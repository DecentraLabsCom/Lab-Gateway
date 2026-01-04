#!/bin/bash
set -euo pipefail

ORIGINAL_ENTRYPOINT="/usr/local/bin/docker-entrypoint.sh"
ENSURE_SCRIPT="/docker-entrypoint-initdb.d/000-ensure-user.sh"

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
  
  # Wait up to 60 seconds for MySQL to be ready
  for i in {1..60}; do
    if mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
      echo "MySQL is ready. Waiting for Guacamole schema..."
      waited=0
      max_wait=60
      while true; do
        missing_tables=()
        for table in guacamole_entity guacamole_user guacamole_system_permission guacamole_user_permission; do
          exists="$(mysql -u root -p"${MYSQL_ROOT_PASSWORD}" -N -B -e "SELECT 1 FROM information_schema.tables WHERE table_schema='${MYSQL_DATABASE}' AND table_name='${table}' LIMIT 1" || true)"
          if [[ "${exists}" != "1" ]]; then
            missing_tables+=("${table}")
          fi
        done

        if [[ "${#missing_tables[@]}" -eq 0 ]]; then
          break
        fi

        if [[ "${waited}" -ge "${max_wait}" ]]; then
          echo "Guacamole schema not ready after ${max_wait}s (missing: ${missing_tables[*]}). Running ensure-user anyway."
          break
        fi

        echo "Guacamole schema not ready (missing: ${missing_tables[*]}); waiting..."
        sleep 2
        waited=$((waited + 2))
      done

      echo "MySQL is ready. Running ensure-user script..."
      if [[ -x "${ENSURE_SCRIPT}" ]]; then
        "${ENSURE_SCRIPT}"
      else
        bash "${ENSURE_SCRIPT}"
      fi
      break
    fi
    
    if [[ $i -eq 60 ]]; then
      echo "Warning: MySQL did not become ready in time. Ensure-user script not executed." >&2
    fi
    
    sleep 1
  done
else
  echo "Warning: ensure script ${ENSURE_SCRIPT} not found" >&2
fi

wait "${child_pid}"
