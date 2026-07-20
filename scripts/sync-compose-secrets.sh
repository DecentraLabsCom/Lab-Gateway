#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/.env}"
SECRETS_DIR="${ROOT_DIR}/secrets"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Environment file not found: ${ENV_FILE}" >&2
    exit 1
fi

umask 077
mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

read_env_value() {
    local key="$1"
    awk -F= -v key="${key}" '$1 == key {
        sub(/^[^=]*=/, "")
        sub(/\r$/, "")
        print
        exit
    }' "${ENV_FILE}"
}

write_secret() {
    local secret_name="$1"
    local env_key="$2"
    read_env_value "${env_key}" > "${SECRETS_DIR}/${secret_name}"
    chmod 640 "${SECRETS_DIR}/${secret_name}"
}

write_secret mysql_root_password MYSQL_ROOT_PASSWORD
write_secret guacamole_mysql_password GUACAMOLE_MYSQL_PASSWORD
write_secret blockchain_mysql_password BLOCKCHAIN_MYSQL_PASSWORD
write_secret ops_backend_mysql_password OPS_BACKEND_MYSQL_PASSWORD
write_secret ops_guacamole_mysql_password OPS_GUACAMOLE_MYSQL_PASSWORD
write_secret guac_admin_pass GUAC_ADMIN_PASS
write_secret admin_access_token ADMIN_ACCESS_TOKEN
write_secret lab_manager_token LAB_MANAGER_TOKEN
write_secret ops_internal_auth_token OPS_INTERNAL_AUTH_TOKEN
write_secret ops_secrets_key OPS_SECRETS_KEY
write_secret auth_access_code_redeemer_token AUTH_ACCESS_CODE_REDEEMER_TOKEN
write_secret session_observation_ingest_token SESSION_OBSERVATION_INGEST_TOKEN
write_secret guacamole_provisioner_token GUACAMOLE_PROVISIONER_TOKEN
write_secret aas_service_token AAS_SERVICE_TOKEN
write_secret lab_admin_backend_token LAB_ADMIN_BACKEND_TOKEN
write_secret fmu_station_internal_token FMU_STATION_INTERNAL_TOKEN
write_secret auth_session_ticket_internal_token AUTH_SESSION_TICKET_INTERNAL_TOKEN
write_secret session_observer_signing_secret SESSION_OBSERVER_SIGNING_SECRET
write_secret fmu_proxy_signing_key FMU_PROXY_SIGNING_KEY

host_uid="$(read_env_value HOST_UID)"
host_gid="$(read_env_value HOST_GID)"
if [[ "${host_uid}" =~ ^[0-9]+$ && "${host_gid}" =~ ^[0-9]+$ ]]; then
    current_uid="$(id -u)"
    current_gid="$(id -g)"
    if [[ "${current_uid}" != "${host_uid}" || "${current_gid}" != "${host_gid}" ]]; then
        chown "${host_uid}:${host_gid}" "${SECRETS_DIR}" "${SECRETS_DIR}"/*
    fi
    chmod 750 "${SECRETS_DIR}"
else
    echo "HOST_UID/HOST_GID must be numeric in ${ENV_FILE}; cannot assign secret ownership." >&2
    exit 1
fi

echo "Compose secret files synchronized in ${SECRETS_DIR}."
