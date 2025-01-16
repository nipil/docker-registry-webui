#!/bin/bash

set -e -u -o pipefail

function error() {
    echo "ERROR: ${1:-}" >&2
    exit 1
}

[[ -n "${REGISTRY_URL}" ]] || error "REGISTRY_URL env var must be defined"
[[ -n "${REGISTRY_DIR}" ]] || error "REGISTRY_DIR env var must be defined"

AUTH_FILE="--authfile auth.json"

# list available manifests before deletion
find "${REGISTRY_DIR}" | sort > populate-before-deletion.log

# WARNING: skopeo deletes does the following :
# - looks up digest from tag
# - deletes the revision digest (and every tag pointing to it)
# So do not be surprised if more than expected disappears :-)

# delete image to mark manifests as garbage-collectable (blobs are still referenced)
skopeo delete ${AUTH_FILE} docker://${REGISTRY_URL}/docker.io/library/debian:12.9-slim || true

# delete image to mark manifest and blobs as garbage-collectable
skopeo delete ${AUTH_FILE} docker://${REGISTRY_URL}/docker.io/library/debian:trixie-20250113-slim || true

# delete image to mark manifest and blobs as garbage-collectable and then allow for manual repository deletion
skopeo delete ${AUTH_FILE} docker://${REGISTRY_URL}/nginx:1.27.3-alpine || true

# list available manifests before deletion
find "${REGISTRY_DIR}" | sort > populate-after-deletion.log

# show difference
diff -u populate-before-deletion.log populate-after-deletion.log | grep -v '^ '

# show current content
[[ -n "${REGISTRY_URL}" ]] && podman search "${REGISTRY_URL}/"
