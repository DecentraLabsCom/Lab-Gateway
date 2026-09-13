#!/bin/sh
# Load Compose-mounted secrets into the OpenResty process environment.
# The caller sources this file so the exports remain available to nginx/Lua.

load_secret_env() {
    variable="$1"
    path="$2"
    if [ -r "$path" ]; then
        value=$(cat "$path")
        export "$variable=$value"
    fi
}

# Keep browser/admin and internal service credentials out of the OpenResty
# container environment as shown by Compose inspection. Lua still receives
# them through the inherited process environment after this one-time load.
load_secret_env ADMIN_ACCESS_TOKEN /run/secrets/admin_access_token
load_secret_env LAB_MANAGER_TOKEN /run/secrets/lab_manager_token
load_secret_env OPS_INTERNAL_AUTH_TOKEN /run/secrets/ops_internal_auth_token
load_secret_env GUAC_ADMIN_PASS /run/secrets/guac_admin_pass
load_secret_env AUTH_ACCESS_CODE_REDEEMER_TOKEN /run/secrets/auth_access_code_redeemer_token
load_secret_env SESSION_OBSERVATION_INGEST_TOKEN /run/secrets/session_observation_ingest_token
load_secret_env GUACAMOLE_PROVISIONER_TOKEN /run/secrets/guacamole_provisioner_token
load_secret_env AAS_SERVICE_TOKEN /run/secrets/aas_service_token
load_secret_env LAB_ADMIN_BACKEND_TOKEN /run/secrets/lab_admin_backend_token
