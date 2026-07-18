#!/bin/bash
set -euo pipefail

ORIGINAL_ENTRYPOINT="/usr/local/bin/docker-entrypoint.sh"
ENSURE_SCRIPT="/docker-entrypoint-initdb.d/000-ensure-user.sh"

load_secret() {
  local variable="$1"
  local path="$2"
  if [[ -r "${path}" ]]; then
    local value
    value="$(cat "${path}")"
    export "${variable}=${value}"
  fi
}

# Compose secrets are the source of truth. Export them only inside this
# process so the official MySQL entrypoint and the permission reconciler keep
# their existing environment-based contracts without exposing values through
# the Compose service definition.
load_secret MYSQL_ROOT_PASSWORD /run/secrets/mysql_root_password
load_secret GUACAMOLE_MYSQL_PASSWORD /run/secrets/guacamole_mysql_password
load_secret BLOCKCHAIN_MYSQL_PASSWORD /run/secrets/blockchain_mysql_password
load_secret OPS_BACKEND_MYSQL_PASSWORD /run/secrets/ops_backend_mysql_password
load_secret OPS_GUACAMOLE_MYSQL_PASSWORD /run/secrets/ops_guacamole_mysql_password
load_secret GUAC_ADMIN_PASS /run/secrets/guac_admin_pass

if [[ ! -x "${ORIGINAL_ENTRYPOINT}" ]]; then
  echo "Cannot find original MySQL entrypoint at ${ORIGINAL_ENTRYPOINT}" >&2
  exit 1
fi

# Start MySQL in background
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

# Wait for MySQL to be ready before running the ensure-user script
if [[ -f "${ENSURE_SCRIPT}" ]]; then
  echo "Waiting for MySQL to be ready before ensuring user permissions..."

  max_wait="${MYSQL_ENSURE_USER_WAIT_SECONDS:-180}"

  # Wait up to max_wait seconds for MySQL to be ready
  for (( i=1; i<=max_wait; i++ )); do
    if mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
      echo "MySQL is ready. Running ensure-user script..."
      if [[ -x "${ENSURE_SCRIPT}" ]]; then
        "${ENSURE_SCRIPT}"
      else
        bash "${ENSURE_SCRIPT}"
      fi
      break
    fi
    
    if [[ $i -eq $max_wait ]]; then
      echo "Warning: MySQL did not become ready in ${max_wait}s. Ensure-user script not executed." >&2
      echo "Hint: if mysql_data already exists, verify .env MYSQL_ROOT_PASSWORD matches the stored root password." >&2
    fi
    
    sleep 1
  done
else
  echo "Warning: ensure script ${ENSURE_SCRIPT} not found" >&2
fi

wait "${child_pid}"
