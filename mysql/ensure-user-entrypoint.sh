#!/bin/bash
set -euo pipefail

ORIGINAL_ENTRYPOINT="/usr/local/bin/docker-entrypoint.sh"
ENSURE_SCRIPT="/docker-entrypoint-initdb.d/000-ensure-user.sh"

if [[ ! -x "${ORIGINAL_ENTRYPOINT}" ]]; then
  echo "Cannot find original MySQL entrypoint at ${ORIGINAL_ENTRYPOINT}" >&2
  exit 1
fi

"${ORIGINAL_ENTRYPOINT}" "$@" &
child_pid=$!

forward_signal() {
  local signal=$1
  if kill -0 "${child_pid}" 2>/dev/null; then
    kill "-${signal}" "${child_pid}" 2>/dev/null || true
  fi
}

trap 'forward_signal TERM' TERM
trap 'forward_signal INT' INT

if [[ -f "${ENSURE_SCRIPT}" ]]; then
  bash "${ENSURE_SCRIPT}"
else
  echo "Warning: ensure script ${ENSURE_SCRIPT} not found" >&2
fi

wait "${child_pid}"
