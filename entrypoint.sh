#!/bin/bash

# bash "safe mode"
set -e -u -o pipefail

# move to APP directory in order for reload options to work properly
cd $APP_DIR

# ensure using exec in order to forward signals (sigterm, sigkill, etc)
# by avoiding creating a sub-shell, which would prevent transmitting signals
exec \
    python3 -m uvicorn \
    --host $APP_LISTEN_ADDR \
    --port $APP_LISTEN_PORT \
    --app-dir $APP_DIR $APP_MODULE:$APP_ATTRIBUTE \
    "${@}"
