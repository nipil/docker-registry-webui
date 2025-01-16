#!/bin/bash

set -e -u -o pipefail

apt-get update
apt-get install -y --no-install-recommends ca-certificates skopeo podman fuse-overlayfs git

cat <<EOF >/etc/containers/registries.conf.d/registry.conf
unqualified-search-registries = ["registry:5000"]

[[registry]]
location = "registry:5000"
insecure = true
EOF
