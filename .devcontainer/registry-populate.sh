#!/bin/bash

set -e -u -o pipefail

function error() {
    echo "ERROR: ${1:-}" >&2
    exit 1
}

[[ -n "${REGISTRY_URL}" ]] || error "REGISTRY_URL env var must be defined"

CACHE_IMAGE="cache-images.tar"
AUTH_FILE="--authfile auth.json"
SYNC_OPTS="--scoped --preserve-digests ${AUTH_FILE}"

function import_image_cache() {
    local TMP=$(mktemp -d)
    trap "rm -Rf ${TMP}" RETURN
    tar -C "${TMP}" -x -f "${CACHE_IMAGE}"
    skopeo sync --all --src dir "${TMP}" ${SYNC_OPTS} --dest docker "${REGISTRY_URL}"
}

function get_images_from_docker_hub() {
    local TMP=$(mktemp -d)
    trap "rm -Rf ${TMP}" RETURN
    skopeo sync ${SYNC_OPTS} --src yaml .devcontainer/images-single-arch.yml --dest dir "${TMP}"
    skopeo sync --all ${SYNC_OPTS} --src yaml .devcontainer/images-multi-arch.yml --dest dir "${TMP}"
    tar -C "${TMP}" -c -f "${CACHE_IMAGE}" .
}

function main() {
    [[ -f "${CACHE_IMAGE}" ]] || get_images_from_docker_hub
    [[ -f "${CACHE_IMAGE}" ]] && import_image_cache
    [[ -n "${REGISTRY_URL}" ]] && podman search "${REGISTRY_URL}/"
}

main
