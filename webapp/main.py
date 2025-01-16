#!/usr/bin/env python3

import json
import re
import sys
import time
from enum import StrEnum
from logging import getLogger
from pathlib import Path
from typing import ClassVar, Pattern, Self

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
# https://docs.pydantic.dev/1.10/
from pydantic import BaseSettings, BaseModel, Field, validator, ValidationError

logger = getLogger('uvicorn.error')


class Settings(BaseSettings):
    registry_dir: Path
    # short duration so that user sees new repositories
    registry_load_ttl: float = 3
    # short duration so that user sees new tags and revisions
    repository_load_ttl: float = 3


class HashableModel(BaseModel):
    # https://github.com/pydantic/pydantic/issues/1303#issuecomment-2052395207
    def __hash__(self):
        return hash((type(self),) + tuple(self.dict().items()))


class OciDigest(BaseModel):
    value: str

    class Algorithm(StrEnum):
        SHA256 = 'sha256'
        SHA512 = 'sha512'

    class Validator:
        RE_SHA256: ClassVar[str] = 'sha256:[a-f0-9]{64}'
        RE_SHA512: ClassVar[str] = 'sha512:[a-f0-9]{128}'
        RE_VALIDATE: ClassVar[Pattern] = re.compile(f'^({RE_SHA256}|{RE_SHA512})$')

        @classmethod
        def validate(cls, value: str) -> str:
            if cls.RE_VALIDATE.fullmatch(value) is None:
                raise ValueError(f'{value} is not a valid OCI digest')
            return value

    _value = validator('value', allow_reuse=True)(Validator.validate)

    def algorithm(self) -> str:
        return self.Algorithm(self.value.split(':')[0])

    def encoded(self) -> str:
        return self.value.split(':')[1]

    @classmethod
    # PEP 673 : Self not allowed in @staticmethod...
    def from_raw_digest(cls, algorithm: Algorithm, digest: str) -> Self:
        return OciDigest(value=f'{algorithm.value}:{digest}')


def schema_revision_validator(value: int):
    expected = 2
    if value != expected:
        raise ValueError(f'Invalid schemaVersion={value} (must be {expected})')
    return value


class OciMediaType:
    # https://github.com/opencontainers/image-spec/blob/main/media-types.md

    # NOTE : I ignored deprecated 'non-distributable' layer media types on purpose
    oci_descriptor = 'application/vnd.oci.descriptor.v1+json'
    oci_layout = 'application/vnd.oci.layout.header.v1+json'
    oci_image_index = 'application/vnd.oci.image.index.v1+json'
    oci_image_manifest = 'application/vnd.oci.image.manifest.v1+json'
    oci_image_config = 'application/vnd.oci.image.config.v1+json'
    oci_layer_tar = 'application/vnd.oci.image.layer.v1.tar'
    oci_layer_tar_gz = 'application/vnd.oci.image.layer.v1.tar+gzip'
    oci_layer_tar_zstd = 'application/vnd.oci.image.layer.v1.tar+zstd'
    oci_empty = 'application/vnd.oci.empty.v1+json'

    # https://github.com/in-toto/specification/blob/master/in-toto-spec.md
    in_toto = 'application/vnd.in-toto+json'


class OciPlatform(BaseModel):
    # https://github.com/opencontainers/image-spec/blob/main/image-index.md

    architecture: str
    os: str

    os_version: str = Field(default=None, alias='os.version')
    os_features: list[str] = Field(default=None, alias='os.features')
    variant: str = None
    features: list[str] = None


class OciContentDescriptor(BaseModel):
    # https://github.com/opencontainers/image-spec/blob/main/descriptor.md

    mediaType: str
    digest: str
    size: int

    platform: OciPlatform = None
    urls: list[str] = Field(default_factory=list)
    annotations: dict[str, str] = Field(default_factory=dict)
    data: str = None  # base64
    artifactType: str = None


class OciImageManifest(BaseModel):
    # https://github.com/opencontainers/image-spec/blob/main/manifest.md

    schemaVersion: int
    mediaType: str
    artifactType: str = None
    config: OciContentDescriptor
    layers: list[OciContentDescriptor]

    subject: OciContentDescriptor = None
    annotations: dict[str, str] = Field(default_factory=dict)

    _schemaVersion = validator('schemaVersion', allow_reuse=True)(schema_revision_validator)

    @validator('mediaType')
    def media_type_validator(cls, v):
        expected = OciMediaType.oci_image_manifest
        if v != expected:
            raise ValueError(f'Image manifest mediaType must be {expected}')
        return v

    # TODO: implement artefacts ?
    # https://github.com/opencontainers/image-spec/blob/main/manifest.md#guidelines-for-artifact-usage

    def size(self) -> int:
        total = self.config.size
        for layer in self.layers:
            total += layer.size
        return total


class OciImageIndex(BaseModel):
    # https://github.com/opencontainers/image-spec/blob/main/image-index.md

    schemaVersion: int
    mediaType: str

    manifests: list[OciContentDescriptor] = Field(default_factory=list)
    artifactType: str = None
    subject: OciContentDescriptor = None

    _schemaVersion = validator('schemaVersion', allow_reuse=True)(schema_revision_validator)

    @validator('mediaType')
    def media_type_validator(cls, v):
        expected = OciMediaType.oci_image_index
        if v != expected:
            raise ValueError(f'Image manifest mediaType must be {expected}')
        return v


class OciImageConfig(BaseModel):
    # https://github.com/opencontainers/image-spec/blob/main/config.md

    class Config(BaseModel):
        # NOTE: deliberately ignored deprecated ArgsEscaped

        User: str = None
        ExposedPorts: dict[str, dict] = None
        Env: list[str] = None
        Entrypoint: list[str] = None
        Cmd: list[str] = None
        Volumes: dict[str, dict] = None
        WorkingDir: str = None
        Labels: dict[str, str] = None
        StopSignal: str = None
        Memory: int = None
        MemorySwap: int = None
        CpuShares: int = None
        Healthcheck: dict = None

    class RootFilesystem(BaseModel):
        type: str
        diff_ids: list[str]

    class History(BaseModel):
        created: str = None
        author: str = None
        created_by: str = None
        comment: str = None
        empty_layer: bool = None

    architecture: str
    os: str
    rootfs: RootFilesystem

    os_version: str = Field(default=None, alias='os.version')
    os_features: list[str] = Field(default=None, alias='os.features')
    variant: str = None
    created: str = None
    author: str = None
    config: Config = None


class Blob(BaseModel):
    digest: str
    content: bytes

    last_load: float = Field(default=0)
    _digest = validator('digest', allow_reuse=True)(OciDigest.Validator.validate)


class Tag(BaseModel):
    name: str
    digest: str

    _digest = validator('digest', allow_reuse=True)(OciDigest.Validator.validate)


class Revision(BaseModel):
    digest: str

    tags: list[Tag] = Field(default_factory=list)
    _digest = validator('digest', allow_reuse=True)(OciDigest.Validator.validate)


class Repository(BaseModel):
    path: Path
    name: str

    cached_revisions: dict[str, Revision] = Field(default_factory=dict)
    last_load: float = Field(default=0)

    load_ttl: ClassVar[float] = 0

    def revisions_path(self):
        # docker registry v2 uses sha256 as digest algorithm
        return self.path / '_manifests' / 'revisions' / 'sha256'

    def tags_path(self):
        return self.path / '_manifests' / 'tags'

    def hash_for_tag(self, tag: str) -> OciDigest:
        path = self.tags_path() / tag / 'current' / 'link'
        with path.open('r') as f:
            return OciDigest(value=f.read())

    def load(self) -> None:
        # load detected revisions
        path = self.revisions_path()
        self.cached_revisions.clear()
        for child in path.iterdir():
            # docker registry v2 uses sha256 as digest algorithm
            digest = OciDigest.from_raw_digest(OciDigest.Algorithm.SHA256, child.name)
            # TODO: check that revision holds an actual link (it would not once garbage-collected) to prevent 404
            revision = Revision(digest=digest.value)
            # use value instead of OciDigest ("unhashable type: 'dict'")
            self.cached_revisions[digest.value] = revision
        # load detected tags
        path = self.tags_path()
        tags: list[Tag] = []
        for child in path.iterdir():
            # docker registry v2 uses sha256 as digest algorithm
            digest = self.hash_for_tag(child.name)
            # use value instead of OciDigest ("unhashable type: 'dict'")
            tag = Tag(name=child.name, digest=digest.value)
            tags.append(tag)
        #  link tags to revisions
        for tag in tags:
            # use value instead of OciDigest ("unhashable type: 'dict'")
            self.cached_revisions[tag.digest].tags.append(tag)
        self.last_load = time.time()

    def revisions(self) -> list[tuple[OciDigest, Revision]]:
        return [(OciDigest(value=digest), revision)
                for digest, revision in self.cached_revisions.items()]

    def revision(self, digest: OciDigest) -> Revision:
        try:
            # use value instead of OciDigest ("unhashable type: 'dict'")
            return self.cached_revisions[digest.value]
        except KeyError:
            raise HTTPException(404, 'Revision not found')


class Registry(BaseModel):
    root: Path

    cached_repositories: dict[str, Repository] = Field(default_factory=dict)
    last_load: float = Field(default=0)

    load_ttl: ClassVar[float] = 0

    def base_v2_path(self) -> Path:
        return self.root / 'docker' / 'registry' / 'v2'

    def repositories_path(self) -> Path:
        return self.base_v2_path() / 'repositories'

    def blobs_path(self) -> Path:
        return self.base_v2_path() / 'blobs'

    def blob_path(self, digest: OciDigest) -> Path:
        # docker registry v2 uses sha256 as digest algorithm
        if digest.algorithm() != OciDigest.Algorithm.SHA256:
            raise HTTPException(500, 'Invalid digest type')
        digest = digest.encoded()
        return self.blobs_path() / 'sha256' / digest[0:2] / digest / 'data'

    def load(self) -> None:
        path = self.repositories_path()
        self.cached_repositories.clear()
        for manifest_path in path.rglob('_manifests'):
            repo_path = manifest_path.parent
            scoped_name = repo_path.relative_to(path).as_posix()
            repo = Repository(path=repo_path, name=scoped_name)
            self.cached_repositories[scoped_name] = repo
        self.last_load = time.time()

    def repositories(self) -> dict[str, Repository]:
        now = time.time()
        if now > self.last_load + self.load_ttl:
            self.load()
        return self.cached_repositories

    def repository(self, name: str) -> Repository:
        repositories = self.repositories()
        try:
            repository = repositories[name]
        except KeyError:
            raise HTTPException(404, 'Repository not found')
        now = time.time()
        if now > repository.last_load + repository.load_ttl:
            repository.load()
        return repository

    def blob(self, digest: OciDigest) -> Blob:
        """Blobs are always read from disk to save memory"""
        path = self.blob_path(digest)
        try:
            with open(path, 'rb') as f:
                return Blob(digest=digest.value, content=f.read())
        except FileNotFoundError:
            raise HTTPException(404, 'Blob not found')
        except OSError as e:
            logger.error(f'Failed to read blob {digest.value}: {e}')
            raise HTTPException(500, 'Internal Server Error (Blob)')

    def manifest(self, repository: str, digest: OciDigest) -> OciImageManifest | OciImageIndex:
        # go through repository revisions to only allow access to manifests/indexes
        repository = self.repository(repository)
        revision = repository.revision(digest)
        digest = OciDigest(value=revision.digest)
        blob = self.blob(digest)
        # Manifests are JSON-blobs
        try:
            data = json.loads(blob.content)
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse manifest {revision.digest}: {e}')
            raise HTTPException(500, 'Internal Server Error (JSON-blob)')
        # handle different types of OCI images
        if data.get('mediaType') == OciMediaType.oci_image_index:
            try:
                return OciImageIndex(**data)
            except ValidationError as e:
                logger.error(e)
                raise HTTPException(500, 'Internal Server Error (OciImageIndex)')
        elif data.get('mediaType') == OciMediaType.oci_image_manifest:
            try:
                return OciImageManifest(**data)
            except ValidationError as e:
                logger.error(e)
                raise HTTPException(500, 'Internal Server Error (OciImageManifest)')
        else:
            raise HTTPException(500, 'Internal Server Error (MediaType)')

    def config(self, digest: OciDigest):
        """Should only be called from access-verified digests, to prevent open access to blobs"""
        blob = self.blob(digest)
        try:
            data = json.loads(blob.content)
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse config {digest.value}: {e}')
            raise HTTPException(500, 'Internal Server Error (JSON-blob)')
        return OciImageConfig(**data)


class RegistryApp(FastAPI):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        logger.info('Initializing registry webapp')
        self.state.settings = self.get_settings()
        self.state.registry = Registry(root=self.state.settings.registry_dir)
        Registry.load_ttl = self.state.settings.registry_load_ttl
        Repository.load_ttl = self.state.settings.repository_load_ttl

    @staticmethod
    def get_settings() -> Settings:
        try:
            # noinspection PyArgumentList
            return Settings()
        except ValidationError as e:
            logger.error(e)
            sys.exit(1)


app = RegistryApp()


@app.get('/repositories')
async def read_repositories():
    repositories = app.state.registry.repositories()
    # raise HTTPException(500, 'TEST')
    # return None
    # return {'repositories': []}
    return {'repositories': list(repositories.keys())}


@app.get('/repositories/{full_name:path}')
async def read_repository(full_name: str):
    repository = app.state.registry.repository(full_name)
    # raise HTTPException(500, 'TEST')
    # return None
    # return {'repositories': []}
    return {
        'revisions': {
            digest.value: {
                'tags': [tag.name for tag in revision.tags]
            }
            for (digest, revision) in repository.revisions()
        }
    }


@app.get('/revisions/{revision}/repository/{full_name:path}')
async def read_revision(revision: str, full_name: str):
    digest = OciDigest(value=revision)
    manifest: OciImageManifest | OciImageIndex = app.state.registry.manifest(full_name, digest)
    # raise HTTPException(500, 'TEST')
    # return None
    if isinstance(manifest, OciImageIndex):
        # return {'type': 'index'}
        # return {'type': 'index', 'manifests': []}
        return {
            'type': 'index',
            'manifests': [
                {
                    'digest': OciDigest(value=m.digest).value,
                    'platform': f'{m.platform.os}-{m.platform.architecture}'
                }
                for m in manifest.manifests
            ]
        }
    elif isinstance(manifest, OciImageManifest):
        config = app.state.registry.config(OciDigest(value=manifest.config.digest))
        # return {'type': 'image'}
        return {
            'type': 'image',
            'metadata': {
                'created': config.created,
                'author': config.author,
                'size': manifest.size(),
                'annotations': manifest.annotations,
            },
            'configuration': {
                'environment': config.config.Env,
                'entrypoint': config.config.Entrypoint,
                'command': config.config.Cmd,
                'working_directory': config.config.WorkingDir
            },
            'layers': [
                {
                    "media_type": layer.mediaType,
                    "digest": layer.digest,
                    "size": layer.size
                }
                for layer in manifest.layers
            ]
        }
    else:
        raise HTTPException(500, 'Internal Server Error (unknown OCI Manifest media type)')


# fallback to static files
app.mount('/', StaticFiles(directory='static', html=True), name='static')
