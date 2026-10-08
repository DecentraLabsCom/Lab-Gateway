#!/bin/sh
set -eu
if [ "${1:-}" = "list-sessions" ]; then
    exit 0
fi
exit 2
