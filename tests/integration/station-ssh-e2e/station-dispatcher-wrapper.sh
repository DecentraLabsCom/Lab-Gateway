#!/bin/sh
set -eu
exec sudo -n -H --user=labstationd -- \
    /usr/local/lib/decentralabs/labstation-dispatcher
