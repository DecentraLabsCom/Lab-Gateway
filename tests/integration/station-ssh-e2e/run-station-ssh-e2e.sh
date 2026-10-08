#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
GATEWAY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
LAB_STATION_LINUX_DIR=${LAB_STATION_LINUX_DIR:-"$GATEWAY_ROOT/../Lab Station Linux"}
test -f "$LAB_STATION_LINUX_DIR/go.mod" || { echo 'Lab Station Linux checkout is unavailable.' >&2; exit 2; }

KEY_DIR=$(mktemp -d)
cleanup() {
    docker compose -f "$SCRIPT_DIR/compose.yml" down --volumes --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$KEY_DIR"
}
trap cleanup EXIT HUP INT TERM
umask 077
ssh-keygen -q -t ed25519 -N '' -C gateway-station-e2e -f "$KEY_DIR/gateway"

export LAB_STATION_LINUX_DIR
export E2E_SSH_PRIVATE_KEY_FILE="$KEY_DIR/gateway"
export E2E_SSH_PUBLIC_KEY_FILE="$KEY_DIR/gateway.pub"
export COMPOSE_PROJECT_NAME=lab-station-ssh-e2e
docker compose -f "$SCRIPT_DIR/compose.yml" up --build --abort-on-container-exit --exit-code-from gateway-test
