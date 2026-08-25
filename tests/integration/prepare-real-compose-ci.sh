#!/usr/bin/env bash
set -Eeuo pipefail

# Build an isolated, disposable configuration for the real Compose resilience
# gate. Production .env files and secrets are never read or overwritten.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_DIR="${REAL_COMPOSE_ENV_DIR:-${RUNNER_TEMP:-$ROOT_DIR/.ci-real-compose-env}}"
ROOT_ENV_FILE="$ENV_DIR/root.env"
BACKEND_ENV_FILE="$ENV_DIR/blockchain-services.env"
OVERRIDE_FILE="$ENV_DIR/secrets.override.yml"

mkdir -p "$ENV_DIR"
cp "$ROOT_DIR/.env.example" "$ROOT_ENV_FILE"
cp "$ROOT_DIR/blockchain-services/.env.example" "$BACKEND_ENV_FILE"

set_env() {
  local key="$1"
  local value="$2"
  local file="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

set_env SERVER_NAME localhost "$ROOT_ENV_FILE"
set_env HTTPS_PORT 443 "$ROOT_ENV_FILE"
set_env HTTP_PORT 80 "$ROOT_ENV_FILE"
set_env OPENRESTY_BIND_ADDRESS 127.0.0.1 "$ROOT_ENV_FILE"
set_env OPENRESTY_BIND_HTTPS_PORT 18483 "$ROOT_ENV_FILE"
set_env OPENRESTY_BIND_HTTP_PORT 18081 "$ROOT_ENV_FILE"
# Compose runs the services that use bind-mounted state as this numeric user.
# Match the runner and materialize the paths before Docker can create them as
# root, otherwise blockchain-services cannot create its persisted keys and
# OpenResty cannot create its development certificate/state files.
host_uid="$(id -u)"
host_gid="$(id -g)"
set_env HOST_UID "$host_uid" "$ROOT_ENV_FILE"
set_env HOST_GID "$host_gid" "$ROOT_ENV_FILE"
mkdir -p "$ROOT_DIR/blockchain-data/keys" "$ROOT_DIR/certs" \
  "$ROOT_DIR/fmu-access-state" "$ROOT_DIR/lab-content" "$ROOT_DIR/ops-data"
chmod 700 "$ROOT_DIR/blockchain-data" "$ROOT_DIR/fmu-access-state" "$ROOT_DIR/ops-data"
chmod 755 "$ROOT_DIR/certs" "$ROOT_DIR/lab-content"
set_env BLOCKCHAIN_SERVICES_ENABLED true "$ROOT_ENV_FILE"
set_env BLOCKCHAIN_SERVICES_MODE provider-consumer "$ROOT_ENV_FILE"
set_env CONTRACT_VERIFICATION_ENABLED false "$ROOT_ENV_FILE"
set_env CONTRACT_EVENT_POLLING_ENABLED false "$ROOT_ENV_FILE"
set_env CONTRACT_EVENT_PERSISTENCE_REQUIRED false "$ROOT_ENV_FILE"
set_env FEATURES_PROVIDERS_ENABLED true "$ROOT_ENV_FILE"
set_env WEBAUTHN_CREDENTIALS_REQUIRE_DATABASE false "$ROOT_ENV_FILE"
set_env INTENTS_AUTH_ENABLED false "$ROOT_ENV_FILE"
set_env INTENT_PAYLOAD_ENCRYPTION_KEY MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= "$ROOT_ENV_FILE"
set_env MYSQL_ROOT_PASSWORD resilience-root-password "$ROOT_ENV_FILE"
set_env MYSQL_DATABASE guacamole_db "$ROOT_ENV_FILE"
set_env BLOCKCHAIN_MYSQL_DATABASE blockchain_services "$ROOT_ENV_FILE"
set_env GUACAMOLE_MYSQL_USER guacamole_app "$ROOT_ENV_FILE"
set_env GUACAMOLE_MYSQL_PASSWORD resilience-guacamole-password "$ROOT_ENV_FILE"
set_env BLOCKCHAIN_MYSQL_USER blockchain_app "$ROOT_ENV_FILE"
set_env BLOCKCHAIN_MYSQL_PASSWORD resilience-blockchain-password "$ROOT_ENV_FILE"
set_env OPS_BACKEND_MYSQL_USER ops_backend "$ROOT_ENV_FILE"
set_env OPS_BACKEND_MYSQL_PASSWORD resilience-ops-backend-password "$ROOT_ENV_FILE"
set_env OPS_GUACAMOLE_MYSQL_USER ops_guac "$ROOT_ENV_FILE"
set_env OPS_GUACAMOLE_MYSQL_PASSWORD resilience-ops-guacamole-password "$ROOT_ENV_FILE"
set_env GUAC_ADMIN_USER admin "$ROOT_ENV_FILE"
set_env GUAC_ADMIN_PASS resilience-guacamole-admin "$ROOT_ENV_FILE"
set_env LAB_MANAGER_TOKEN resilience-lab-manager-token "$ROOT_ENV_FILE"
set_env AUTH_ACCESS_CODE_REDEEMER_TOKEN resilience-redeemer-token "$ROOT_ENV_FILE"
set_env ACCESS_CODE_ENCRYPTION_KEY MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= "$ROOT_ENV_FILE"
set_env SESSION_OBSERVATION_INGEST_TOKEN resilience-observation-token "$ROOT_ENV_FILE"
set_env OPS_INTERNAL_AUTH_TOKEN resilience-ops-internal-token "$ROOT_ENV_FILE"
set_env FMU_RUNNER_ENABLED false "$ROOT_ENV_FILE"
set_env FMU_JWT_AUDIENCE https://localhost:18483/fmu "$ROOT_ENV_FILE"
set_env AAS_ENABLED false "$ROOT_ENV_FILE"
set_env DEMO_LAB_ID "" "$ROOT_ENV_FILE"
set_env DEMO_CONNECTION_ID "" "$ROOT_ENV_FILE"
set_env ACCESS_CODE_REDEEMER_CREDENTIALS_JSON '{}' "$ROOT_ENV_FILE"
set_env SESSION_OBSERVER_CREDENTIALS_JSON '{}' "$ROOT_ENV_FILE"
set_env CORS_ALLOWED_ORIGINS https://localhost "$ROOT_ENV_FILE"

set_env CONTRACT_VERIFICATION_ENABLED false "$BACKEND_ENV_FILE"
set_env CONTRACT_EVENT_POLLING_ENABLED false "$BACKEND_ENV_FILE"
set_env CONTRACT_EVENT_PERSISTENCE_REQUIRED false "$BACKEND_ENV_FILE"
set_env BLOCKCHAIN_SERVICES_MODE provider-consumer "$BACKEND_ENV_FILE"
set_env FEATURES_PROVIDERS_ENABLED true "$BACKEND_ENV_FILE"
set_env WEBAUTHN_CREDENTIALS_REQUIRE_DATABASE false "$BACKEND_ENV_FILE"
set_env INTENTS_AUTH_ENABLED false "$BACKEND_ENV_FILE"
set_env INTENT_PAYLOAD_ENCRYPTION_KEY MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= "$BACKEND_ENV_FILE"
set_env BLOCKCHAIN_MYSQL_USER blockchain_app "$BACKEND_ENV_FILE"
set_env BLOCKCHAIN_MYSQL_PASSWORD resilience-blockchain-password "$BACKEND_ENV_FILE"

declare -A secrets=(
  [mysql_root_password]=resilience-root-password
  [guacamole_mysql_password]=resilience-guacamole-password
  [blockchain_mysql_password]=resilience-blockchain-password
  [ops_backend_mysql_password]=resilience-ops-backend-password
  [ops_guacamole_mysql_password]=resilience-ops-guacamole-password
  [guac_admin_pass]=resilience-guacamole-admin
  [admin_access_token]=resilience-admin-token
  [lab_manager_token]=resilience-lab-manager-token
  [ops_internal_auth_token]=resilience-ops-internal-token
  [ops_secrets_key]=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=
  [auth_access_code_redeemer_token]=resilience-redeemer-token
  [session_observation_ingest_token]=resilience-observation-token
  [guacamole_provisioner_token]=resilience-provisioner-token
  [reservation_projection_token]=resilience-projection-token
  [aas_service_token]=resilience-aas-token
  [lab_admin_backend_token]=resilience-lab-admin-token
  [fmu_station_internal_token]=resilience-station-token
  [auth_session_ticket_internal_token]=resilience-session-ticket-token
  [session_observer_signing_secret]=resilience-observer-secret
  [fmu_proxy_signing_key]=resilience-fmu-proxy-key
)

printf 'secrets:\n' > "$OVERRIDE_FILE"
for name in "${!secrets[@]}"; do
  secret_file="$ENV_DIR/$name"
  printf '%s\n' "${secrets[$name]}" > "$secret_file"
  printf '  %s:\n    file: %s\n' "$name" "$secret_file" >> "$OVERRIDE_FILE"
done

# A developer may already have the production stack running. Explicit /24s
# keep this disposable project independent from Docker's exhausted default
# address pool and make parallel CI jobs deterministic.
compose_networks=(
  gateway_public gateway_backend gateway_guacamole ops_control ops_backend
  ops_guacamole guacd_net database_backend database_guacamole database_ops
  fmu_edge fmu_control fmu_aas fmu_aas_ops fmu_local_edge fmu_auth aas_data
)
printf 'networks:\n' >> "$OVERRIDE_FILE"
network_index=0
for network in "${compose_networks[@]}"; do
  printf '  %s:\n    ipam:\n      config:\n        - subnet: 10.250.%s.0/24\n' "$network" "$network_index" >> "$OVERRIDE_FILE"
  network_index=$((network_index + 1))
done

if [[ -n "${GITHUB_ENV:-}" ]]; then
  {
    printf 'COMPOSE_STACK_ROOT_ENV_FILE=%s\n' "$ROOT_ENV_FILE"
    printf 'COMPOSE_STACK_BACKEND_ENV_FILE=%s\n' "$BACKEND_ENV_FILE"
    printf 'COMPOSE_STACK_OVERRIDE_FILE=%s\n' "$OVERRIDE_FILE"
    printf 'COMPOSE_STACK_OPENRESTY_URL=https://127.0.0.1:18483\n'
  } >> "$GITHUB_ENV"
fi

echo "Prepared isolated real Compose configuration in $ENV_DIR"
