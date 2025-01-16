# docker-registry-webui

This is a minimalist UI for the standard `docker-registry` now known
as "[CNCF distribution](https://distribution.github.io/distribution/)".

Supports

- listing and searching all repositories, and all revisions and tags in them
- index manifests : for multi-arch images and listing their platform images
- image manifest : display main properties

No implemented

- accessing layer contents
- accessing stored artefacts

Sample interface :

![Sample interface](https://raw.githubusercontent.com/nipil/docker-registry-webui/refs/heads/main/sample.png)

## Configuration

See `Dockerfile` ENV variables for application configuration :

- The `REGISTRY_DIR` must point to *the folder* holding the files for a running `docker-registry` instance.

## Docker run

Build the image, then mount a folder (either bind or volume) to use as data source :

    docker build -i -t webui .
    docker run -p 8000:8000 -v ./path/to/registry/files:/data -e REGISTRY_DIR="/data" --rm -i -t webui

## Docker compose

See `docker-compose.yaml` services and adapt their configuration to suit your needs :

- Webapp
    - pay attention to `REGISTRY_DIR`, as stated above,
- Registry
    - take a look at the Registry configuration manual
        - https://distribution.github.io/distribution/about/configuration/

Then :

        docker compose up

Compose is only really useful for debugging (as there is only one dependency)
or in case you want to add services (reverse-proxy and all that).

##    

A note about deletion

- deletion is disabled by default in the CNCF registry
- but deletion is enabled by default in this project's compose file (see `REGISTRY_STORAGE_DELETE_ENABLED`)
    - turn it off to run a push-only registry (by the way most registries do not allow deletions)

## Development

### Venv

- Create and activate `venv`

- Install packages : `pip install -r requirements.txt`

- Change to `webapp` directory

- Run the application server : `uvicorn main:app --reload`

### Devcontainer

- Open as dev container

- Run the application :

        /entrypoint.sh --reload

- Go to http://localhost:8000

- Edit your code and files

### Garbage collection after deletion

Take note of the **OFFLINE** garbage collection instructions if deletion was enabled :

- read https://distribution.github.io/distribution/about/garbage-collection/

How to do garbage collection :

- `docker compose stop` (or "Reopen locally" in VS code)
- `docker run --rm -v docker-registry-webui_registry-files:/var/lib/registry --entrypoint /bin/sh -it registry:2`
  to get into a temporary registry container with your volume data mounted in the default configuration place
- `registry garbage-collect --delete-untagged=true /etc/docker/registry/config.yml`
  in the container to prune registry files
    - WARNING : repository folders (and revision folders) with no remaining revisions are **not** removed
      by the upstream tool, so will still appear in the webapp !
    - INFO : if you want to remove empty repository/revision directory, do it manually :
        - https://forums.docker.com/t/delete-repository-from-v2-private-registry/16767/5
- `exit` the temporary container
- `docker compose start` your existing containers (or )

### Pre-populating registry

*Requirement*: Docker Hub login

See `Dockerfile` ENV variables for application configuration :

- The `REGISTRY_DIR` must point to *the folder* holding the files for a running `docker-registry` instance.


- required to synchronize images into local private registry
- If you activated 2FA, create a personnal token : https://app.docker.com/settings/personal-access-tokens
- Choose the following configuration :
    - authorizations : public repo read only
    - expiry : none

Login to Docker Hub

        skopeo login docker.io --authfile auth.json

Populate registry :

        .devcontainer/registry-populate.sh

Remove some images :

        .devcontainer/registry-prune.sh

## BUGS

- devcontainer: allow deletion on docker-registry
