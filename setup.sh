#!/bin/bash

# =================================================================
# DecentraLabs Gateway - Full Version Setup Script (Linux/macOS)
# Complete blockchain-based authentication system with blockchain-services
# =================================================================

set -euo pipefail
# Configuration, key material, and generated credentials are private host
# state.  New files therefore start with owner-only permissions; the explicit
# chmod calls below also repair permissions on files from older installations.
umask 077

ROOT_ENV_FILE=".env"
BLOCKCHAIN_ENV_FILE="blockchain-services/.env"
compose_cmd="docker compose"
compose_min_version="2.14.0"
compose_files=""
compose_profiles=""
cf_enabled=false
certbot_enabled=false
aas_bundled=false
fmu_runner_enabled=false
setup_python_cmd=""
existing_mysql_root_password=""
existing_guacamole_mysql_password=""
existing_blockchain_mysql_password=""
existing_ops_backend_mysql_password=""
existing_ops_guacamole_mysql_password=""
existing_ops_secrets_key=""
existing_basyx_mongo_root_password=""
existing_basyx_mongo_password=""
existing_aas_allowed_hosts=""
existing_aas_service_token=""

echo "DecentraLabs Gateway - Full Version Setup"
echo "=========================================="
echo

update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"
    local escaped_value

    # Escape sed replacement metacharacters before interpolating user-supplied
    # URLs, passwords, tokens, and other environment values.
    escaped_value=$(printf '%s' "$value" | sed 's/[\\&|]/\\&/g')

    if grep -qE "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
    else
        printf '%s\n' "${key}=${value}" >> "$file"
    fi
}

migrate_saml_env() {
    "$setup_python_cmd" scripts/migrate-saml-env.py \
        --env "$BLOCKCHAIN_ENV_FILE" \
        --template "blockchain-services/.env.example"
}

secure_gateway_state() {
    # The first invocation happens before state directories are created, so
    # skip absent paths; once a path exists, a failed permission repair is a
    # hard error rather than a silently weakened deployment.
    if [ -f "$ROOT_ENV_FILE" ] && [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
        chmod 600 "$ROOT_ENV_FILE" "$BLOCKCHAIN_ENV_FILE" || {
            echo "Unable to restrict gateway environment files to mode 0600." >&2
            return 1
        }
    fi
    for state_dir in certs blockchain-data ops-data secrets; do
        if [ -d "$state_dir" ]; then
            chmod 700 "$state_dir" || {
                echo "Unable to restrict state directory permissions: $state_dir" >&2
                return 1
            }
        fi
    done
    # Private keys, Fernet/observer material, and credential spools must never
    # be readable by other local users.  Public certificates remain readable
    # by the gateway process through its owner/group mapping.
    local existing_dirs=()
    for state_dir in certs blockchain-data ops-data secrets; do
        [ -d "$state_dir" ] && existing_dirs+=("$state_dir")
    done
    if [ "${#existing_dirs[@]}" -gt 0 ] && ! find "${existing_dirs[@]}" -type f \
        \( -name '*.key' -o -name 'privkey.pem' -o -name 'private_key.pem' \
           -o -name 'previous_private_key.pem' -o -name '*secret*' \
           -o -name '*credential*' -o -name '*.json' \) \
        -exec chmod 600 {} +; then
        echo "Unable to restrict private key and credential file permissions." >&2
        return 1
    fi
}

write_compose_secret() {
    local secret_name="$1"
    local env_key="$2"
    local value

    value="$(get_env_default "$env_key" "$ROOT_ENV_FILE")"
    printf '%s' "$value" > "secrets/$secret_name"
    chmod 600 "secrets/$secret_name"
}

sync_compose_secrets() {
    mkdir -p secrets
    chmod 700 secrets

    write_compose_secret mysql_root_password MYSQL_ROOT_PASSWORD
    write_compose_secret guacamole_mysql_password GUACAMOLE_MYSQL_PASSWORD
    write_compose_secret blockchain_mysql_password BLOCKCHAIN_MYSQL_PASSWORD
    write_compose_secret ops_backend_mysql_password OPS_BACKEND_MYSQL_PASSWORD
    write_compose_secret ops_guacamole_mysql_password OPS_GUACAMOLE_MYSQL_PASSWORD
    write_compose_secret guac_admin_pass GUAC_ADMIN_PASS
    write_compose_secret admin_access_token ADMIN_ACCESS_TOKEN
    write_compose_secret lab_manager_token LAB_MANAGER_TOKEN
    write_compose_secret ops_internal_auth_token OPS_INTERNAL_AUTH_TOKEN
    write_compose_secret ops_secrets_key OPS_SECRETS_KEY
    write_compose_secret auth_access_code_redeemer_token AUTH_ACCESS_CODE_REDEEMER_TOKEN
    write_compose_secret session_observation_ingest_token SESSION_OBSERVATION_INGEST_TOKEN
    write_compose_secret guacamole_provisioner_token GUACAMOLE_PROVISIONER_TOKEN
    write_compose_secret aas_service_token AAS_SERVICE_TOKEN
    write_compose_secret lab_admin_backend_token LAB_ADMIN_BACKEND_TOKEN
    write_compose_secret fmu_station_internal_token FMU_STATION_INTERNAL_TOKEN
    write_compose_secret auth_session_ticket_internal_token AUTH_SESSION_TICKET_INTERNAL_TOKEN
    write_compose_secret session_observer_signing_secret SESSION_OBSERVER_SIGNING_SECRET
    write_compose_secret fmu_proxy_signing_key FMU_PROXY_SIGNING_KEY
}

get_env_default() {
    local key="$1"
    local file="$2"
    local value=""
    if [ -f "$file" ]; then
        value=$(grep -E "^${key}=" "$file" | head -n 1 | cut -d'=' -f2-)
        value="${value%$'\r'}"
    fi
    echo "$value"
}

is_placeholder_secret() {
    local raw="$1"
    local lower
    lower="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -d ' \r\n\t')"
    case "$lower" in
        ""|changeme|change_me|secure_password|db_password|your_password|password|test)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

remove_env_var() {
    local file="$1"
    local key="$2"

    if [ -f "$file" ]; then
        sed -i "/^${key}=.*/d" "$file"
    fi
}

remove_gateway_managed_backend_env() {
    if [ ! -f "$BLOCKCHAIN_ENV_FILE" ]; then
        return
    fi

    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_ACCESS_TOKEN"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_ACCESS_TOKEN_HEADER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_ACCESS_TOKEN_COOKIE"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_ACCESS_TOKEN_REQUIRED"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_DASHBOARD_LOCAL_ONLY"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_DASHBOARD_ALLOW_PRIVATE"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "SECURITY_ALLOW_PRIVATE_NETWORKS"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "ADMIN_ALLOWED_CIDRS"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "LAB_MANAGER_TOKEN"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "LAB_MANAGER_TOKEN_HEADER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "LAB_MANAGER_TOKEN_COOKIE"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "LAB_MANAGER_ALLOWED_CIDRS"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_INTERNAL_AUTH_TOKEN"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_INTERNAL_AUTH_HEADER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "GUACAMOLE_MYSQL_USER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "GUACAMOLE_MYSQL_PASSWORD"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "BLOCKCHAIN_MYSQL_USER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "BLOCKCHAIN_MYSQL_PASSWORD"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_BACKEND_MYSQL_USER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_BACKEND_MYSQL_PASSWORD"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_GUACAMOLE_MYSQL_USER"
    remove_env_var "$BLOCKCHAIN_ENV_FILE" "OPS_GUACAMOLE_MYSQL_PASSWORD"
}

# Check prerequisites
echo "Checking prerequisites..."
if command -v python3 >/dev/null 2>&1; then
    setup_python_cmd="python3"
elif command -v python >/dev/null 2>&1; then
    setup_python_cmd="python"
fi
if [ -z "$setup_python_cmd" ] || ! "$setup_python_cmd" -c \
    'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
    echo "Python 3 is required for the SAML environment migration." >&2
    echo "   Install Python 3 and rerun setup.sh." >&2
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "Docker Compose V2 is not installed."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

compose_version="$(docker compose version --short 2>/dev/null || true)"
if [ -z "$compose_version" ]; then
    echo "Unable to determine the Docker Compose plugin version." >&2
    echo "   Run: docker compose version" >&2
    exit 1
fi

if ! "$setup_python_cmd" - "$compose_min_version" "$compose_version" <<'PY'
import re
import sys

def parse_version(value):
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        raise SystemExit(2)
    return tuple(int(part or 0) for part in match.groups())

required = parse_version(sys.argv[1])
installed = parse_version(sys.argv[2])
raise SystemExit(0 if installed >= required else 1)
PY
then
    echo "Docker Compose $compose_version is unsupported; version $compose_min_version or newer is required." >&2
    echo "   Visit: https://docs.docker.com/compose/install/" >&2
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo "Git is required to initialize blockchain-services."
    exit 1
fi

echo "Docker, Docker Compose $compose_version, and Git are available"
echo

echo "Ensuring blockchain-services submodule is present..."
git submodule update --init --recursive blockchain-services
echo "blockchain-services submodule ready."
echo

existing_mysql_root_password="$(get_env_default "MYSQL_ROOT_PASSWORD" "$ROOT_ENV_FILE")"
existing_guacamole_mysql_password="$(get_env_default "GUACAMOLE_MYSQL_PASSWORD" "$ROOT_ENV_FILE")"
existing_blockchain_mysql_password="$(get_env_default "BLOCKCHAIN_MYSQL_PASSWORD" "$ROOT_ENV_FILE")"
existing_ops_backend_mysql_password="$(get_env_default "OPS_BACKEND_MYSQL_PASSWORD" "$ROOT_ENV_FILE")"
existing_ops_guacamole_mysql_password="$(get_env_default "OPS_GUACAMOLE_MYSQL_PASSWORD" "$ROOT_ENV_FILE")"
existing_ops_secrets_key="$(get_env_default "OPS_SECRETS_KEY" "$ROOT_ENV_FILE")"
existing_basyx_mongo_root_password="$(get_env_default "BASYX_MONGO_ROOT_PASSWORD" "$ROOT_ENV_FILE")"
existing_basyx_mongo_password="$(get_env_default "BASYX_MONGO_PASSWORD" "$ROOT_ENV_FILE")"
existing_aas_allowed_hosts="$(get_env_default "AAS_ALLOWED_HOSTS" "$ROOT_ENV_FILE")"
existing_aas_service_token="$(get_env_default "AAS_SERVICE_TOKEN" "$ROOT_ENV_FILE")"

# Check if .env already exists
if [ -f "$ROOT_ENV_FILE" ]; then
    echo ".env file already exists!"
    read -p "Do you want to overwrite it? (y/N): " overwrite
    overwrite=$(echo "$overwrite" | tr -d ' ')
    if [ "$overwrite" = "Y" ] || [ "$overwrite" = "y" ]; then
        cp .env.example "$ROOT_ENV_FILE"
        echo "Overwritten .env file from template"
    else
        echo "Keeping existing .env file."
    fi
else
    cp .env.example "$ROOT_ENV_FILE"
    echo "Created .env file from template"
fi
echo

# Ensure blockchain-services/.env exists
if [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
    echo "blockchain-services/.env already exists."
else
    cp blockchain-services/.env.example "$BLOCKCHAIN_ENV_FILE"
    echo "Created blockchain-services/.env from template"
fi
migrate_saml_env
remove_gateway_managed_backend_env
echo

# Database Passwords Configuration
echo
echo "Database Passwords"
echo "=================="
echo "Enter database passwords (leave empty for auto-generated):"
read -p "MySQL root password: " mysql_root_password

if [ -z "$mysql_root_password" ]; then
    if [ -n "$existing_mysql_root_password" ] && ! is_placeholder_secret "$existing_mysql_root_password"; then
        mysql_root_password="$existing_mysql_root_password"
        echo "Reusing existing MySQL root password from .env"
    else
        mysql_root_password="R00t_$(openssl rand -hex 16 2>/dev/null || echo P@ss_${RANDOM}_$(date +%s))"
        echo "Generated root password: $mysql_root_password"
    fi
fi

# Generate independent runtime credentials. They are intentionally not
# prompted individually: operators only need to protect the resulting .env,
# while each container receives the minimum principal it requires.
guacamole_mysql_password="$existing_guacamole_mysql_password"
blockchain_mysql_password="$existing_blockchain_mysql_password"
ops_backend_mysql_password="$existing_ops_backend_mysql_password"
ops_guacamole_mysql_password="$existing_ops_guacamole_mysql_password"
if [ -z "$guacamole_mysql_password" ] || is_placeholder_secret "$guacamole_mysql_password"; then
    guacamole_mysql_password="GuacApp_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi
if [ -z "$blockchain_mysql_password" ] || is_placeholder_secret "$blockchain_mysql_password"; then
    blockchain_mysql_password="ChainApp_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi
if [ -z "$ops_backend_mysql_password" ] || is_placeholder_secret "$ops_backend_mysql_password"; then
    ops_backend_mysql_password="OpsBackend_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi
if [ -z "$ops_guacamole_mysql_password" ] || is_placeholder_secret "$ops_guacamole_mysql_password"; then
    ops_guacamole_mysql_password="OpsGuac_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi
ops_secrets_key="$existing_ops_secrets_key"
if [ -z "$ops_secrets_key" ] || is_placeholder_secret "$ops_secrets_key"; then
    ops_secrets_key="$(openssl rand -base64 32 | tr -d '\n=' | tr '+/' '-_')"
fi

# Bundled BaSyx/Mongo uses separate alphanumeric credentials so they are safe
# in the Mongo URI and cannot be reused for MySQL or application principals.
basyx_mongo_root_password="$existing_basyx_mongo_root_password"
basyx_mongo_password="$existing_basyx_mongo_password"
if [ -z "$basyx_mongo_root_password" ] || is_placeholder_secret "$basyx_mongo_root_password"; then
    basyx_mongo_root_password="AasRoot_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi
if [ -z "$basyx_mongo_password" ] || is_placeholder_secret "$basyx_mongo_password"; then
    basyx_mongo_password="AasApp_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
fi

# Update database credentials only in the gateway root env (.env). The
# blockchain-services submodule env is kept free of gateway-managed secrets.
update_env_var "$ROOT_ENV_FILE" "MYSQL_ROOT_PASSWORD" "$mysql_root_password"
update_env_var "$ROOT_ENV_FILE" "GUACAMOLE_MYSQL_USER" "guacamole_app"
update_env_var "$ROOT_ENV_FILE" "GUACAMOLE_MYSQL_PASSWORD" "$guacamole_mysql_password"
update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_MYSQL_USER" "blockchain_app"
update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_MYSQL_PASSWORD" "$blockchain_mysql_password"
update_env_var "$ROOT_ENV_FILE" "OPS_BACKEND_MYSQL_USER" "ops_backend"
update_env_var "$ROOT_ENV_FILE" "OPS_BACKEND_MYSQL_PASSWORD" "$ops_backend_mysql_password"
update_env_var "$ROOT_ENV_FILE" "OPS_GUACAMOLE_MYSQL_USER" "ops_guac"
update_env_var "$ROOT_ENV_FILE" "OPS_GUACAMOLE_MYSQL_PASSWORD" "$ops_guacamole_mysql_password"
update_env_var "$ROOT_ENV_FILE" "OPS_SECRETS_KEY" "$ops_secrets_key"
update_env_var "$ROOT_ENV_FILE" "BASYX_MONGO_ROOT_USER" "basyx_root"
update_env_var "$ROOT_ENV_FILE" "BASYX_MONGO_ROOT_PASSWORD" "$basyx_mongo_root_password"
update_env_var "$ROOT_ENV_FILE" "BASYX_MONGO_USER" "aas_app"
update_env_var "$ROOT_ENV_FILE" "BASYX_MONGO_PASSWORD" "$basyx_mongo_password"

echo
echo "IMPORTANT: Save these passwords securely!"
echo "   Root password: $mysql_root_password"
echo "   Dedicated database principals: guacamole_app, blockchain_app, ops_backend, ops_guac"
echo

# Guacamole Admin Credentials
echo
echo "Guacamole Admin Credentials"
echo "============================"
echo "These are the credentials for the Guacamole web interface."
echo "A strong admin password is required."
read -p "Guacamole admin username [guacadmin]: " guac_admin_user
read -p "Guacamole admin password (leave empty for auto-generated): " guac_admin_pass

guac_admin_user=$(echo "$guac_admin_user" | tr -d ' ')
guac_admin_pass=$(echo "$guac_admin_pass" | tr -d ' ')

if [ -z "$guac_admin_user" ]; then
    guac_admin_user="guacadmin"
fi
if [ -z "$guac_admin_pass" ]; then
    guac_admin_pass="Guac_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated Guacamole admin password: $guac_admin_pass"
fi

case "$(printf '%s' "$guac_admin_pass" | tr '[:upper:]' '[:lower:]')" in
    guacadmin|changeme|change_me|password|test)
        echo "Refusing to use insecure Guacamole admin password. Set a strong value." >&2
        exit 1
        ;;
esac

update_env_var "$ROOT_ENV_FILE" "GUAC_ADMIN_USER" "$guac_admin_user"
update_env_var "$ROOT_ENV_FILE" "GUAC_ADMIN_PASS" "$guac_admin_pass"
echo

# Admin Access Token
echo "Admin Access Token"
echo "============================"
echo "This token protects /wallet, /billing, /wallet-dashboard, and /billing/admin/** behind OpenResty."
read -p "Admin access token (leave empty for auto-generated): " access_token
access_token=$(echo "$access_token" | tr -d ' ')
case "$(printf '%s' "$access_token" | tr '[:upper:]' '[:lower:]')" in
    ""|"="|changeme|change_me)
        access_token=""
        ;;
esac

if [ -z "$access_token" ]; then
    access_token="acc_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated admin access token: $access_token"
fi

update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN" "$access_token"
update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_HEADER" "X-Access-Token"
update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_COOKIE" "access_token"
update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_REQUIRED" "true"
update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_LOCAL_ONLY" "true"

echo
echo "Wallet Dashboard Access Scope"
echo "============================="
echo "Choose how /wallet-dashboard and wallet/billing admin routes are exposed:"
echo "  1) Localhost only (recommended)"
echo "  2) Private networks + admin access token"
read -p "Choose [1/2] (default: 1): " dashboard_access_scope
dashboard_access_scope=$(echo "$dashboard_access_scope" | tr -d ' ')

if [ "$dashboard_access_scope" = "2" ]; then
    update_env_var "$ROOT_ENV_FILE" "SECURITY_ALLOW_PRIVATE_NETWORKS" "true"
    update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_ALLOW_PRIVATE" "true"
    update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_LOCAL_ONLY" "false"
    read -p "Allowed private CIDRs (comma-separated, leave empty for any private range): " admin_allowed_cidrs
    admin_allowed_cidrs=$(echo "$admin_allowed_cidrs" | sed 's/[[:space:]]//g')
    update_env_var "$ROOT_ENV_FILE" "ADMIN_ALLOWED_CIDRS" "$admin_allowed_cidrs"
    echo "Configured wallet dashboard access for private networks protected by ADMIN_ACCESS_TOKEN."
else
    update_env_var "$ROOT_ENV_FILE" "SECURITY_ALLOW_PRIVATE_NETWORKS" "false"
    update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_ALLOW_PRIVATE" "false"
    update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_LOCAL_ONLY" "true"
    update_env_var "$ROOT_ENV_FILE" "ADMIN_ALLOWED_CIDRS" ""
    echo "Configured wallet dashboard access for localhost only."
fi
echo

# Lab Manager Access Token
echo "Lab Manager Access Token"
echo "========================"
echo "This token protects /lab-manager and /ops when accessed outside private networks."
read -p "Lab Manager token (leave empty for auto-generated): " lab_manager_token
lab_manager_token=$(echo "$lab_manager_token" | tr -d ' ')
case "$(printf '%s' "$lab_manager_token" | tr '[:upper:]' '[:lower:]')" in
    ""|"="|changeme|change_me)
        lab_manager_token=""
        ;;
esac

if [ -z "$lab_manager_token" ]; then
    lab_manager_token="lab_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated Lab Manager token: $lab_manager_token"
fi

update_env_var "$ROOT_ENV_FILE" "LAB_MANAGER_TOKEN" "$lab_manager_token"
update_env_var "$ROOT_ENV_FILE" "LAB_MANAGER_TOKEN_HEADER" "X-Lab-Manager-Token"
update_env_var "$ROOT_ENV_FILE" "LAB_MANAGER_TOKEN_COOKIE" "lab_manager_token"

access_code_redeemer_token=$(get_env_default "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "$ROOT_ENV_FILE")
if [ -z "$access_code_redeemer_token" ] || [ "$access_code_redeemer_token" = "CHANGE_ME" ]; then
    access_code_redeemer_token="acr_$(openssl rand -hex 32 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated access-code redeemer token."
fi
update_env_var "$ROOT_ENV_FILE" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "$access_code_redeemer_token"

access_code_encryption_key=$(get_env_default "ACCESS_CODE_ENCRYPTION_KEY" "$ROOT_ENV_FILE")
if [ -z "$access_code_encryption_key" ] || [ "$access_code_encryption_key" = "CHANGE_ME" ]; then
    access_code_encryption_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n')"
    echo "Generated access-code encryption key."
fi
update_env_var "$ROOT_ENV_FILE" "ACCESS_CODE_ENCRYPTION_KEY" "$access_code_encryption_key"

session_observation_ingest_token=$(get_env_default "SESSION_OBSERVATION_INGEST_TOKEN" "$ROOT_ENV_FILE")
if [ -z "$session_observation_ingest_token" ] || [ "$session_observation_ingest_token" = "CHANGE_ME" ]; then
    session_observation_ingest_token="soi_$(openssl rand -hex 32 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated session-observation ingestion token."
fi
update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVATION_INGEST_TOKEN" "$session_observation_ingest_token"

ops_internal_auth_token=$(get_env_default "OPS_INTERNAL_AUTH_TOKEN" "$ROOT_ENV_FILE")
if [ -z "$ops_internal_auth_token" ] || [ "$ops_internal_auth_token" = "CHANGE_ME" ]; then
    ops_internal_auth_token="ops_$(openssl rand -hex 32 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM}${RANDOM})"
    echo "Generated dedicated Ops Worker internal-auth token."
fi
update_env_var "$ROOT_ENV_FILE" "OPS_INTERNAL_AUTH_TOKEN" "$ops_internal_auth_token"
update_env_var "$ROOT_ENV_FILE" "OPS_INTERNAL_AUTH_HEADER" "X-Ops-Internal-Token"

echo
echo "Lab Manager Backend Allowlist"
echo "============================="
echo "Optional CIDR allowlist enforced by blockchain-services for /lab-admin calls authenticated with LAB_MANAGER_TOKEN."
echo "Leave empty to keep the current behavior and allow any request that already passes the existing admin network policy."
read -p "LAB_MANAGER_ALLOWED_CIDRS [empty]: " lab_manager_allowed_cidrs
lab_manager_allowed_cidrs=$(echo "$lab_manager_allowed_cidrs" | sed 's/[[:space:]]//g')
update_env_var "$ROOT_ENV_FILE" "LAB_MANAGER_ALLOWED_CIDRS" "$lab_manager_allowed_cidrs"
if [ -z "$lab_manager_allowed_cidrs" ]; then
    echo "   * LAB_MANAGER_ALLOWED_CIDRS left empty (no extra /lab-admin CIDR allowlist)."
else
    echo "   * LAB_MANAGER_ALLOWED_CIDRS set to: $lab_manager_allowed_cidrs"
fi
echo

# Domain Configuration
echo "Domain Configuration"
echo "===================="
echo "Enter your domain name (or press Enter for localhost):"
read -p "Domain: " domain
# Clean the domain variable and set default
domain=$(echo "$domain" | tr -d ' ')
if [ -z "$domain" ]; then
    domain="localhost"
fi

# Update .env file with intelligent defaults
if [ "$domain" = "localhost" ]; then
    echo "Configuring for local development..."
    update_env_var "$ROOT_ENV_FILE" "SERVER_NAME" "localhost"
    update_env_var "$ROOT_ENV_FILE" "HTTPS_PORT" "8443"
    update_env_var "$ROOT_ENV_FILE" "HTTP_PORT" "8081"
    update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_ADDRESS" "127.0.0.1"
    update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTPS_PORT" "8443"
    update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTP_PORT" "8081"
    echo "   * Server: https://localhost:8443"
    echo "   * Using development ports (8443/8081)"
else
    echo "Configuring for production..."
    update_env_var "$ROOT_ENV_FILE" "SERVER_NAME" "$domain"
    
    # Ask about deployment mode
    echo
    echo "Deployment Mode"
    echo "---------------"
    echo "How is the gateway exposed to the internet?"
    echo "  1) Direct - Gateway has a public IP (ports bound directly)"
    echo "  2) Router - Behind NAT/router with port forwarding (e.g., router:8043 → host:443)"
    read -p "Choose [1/2] (default: 1): " deploy_mode
    deploy_mode=$(echo "$deploy_mode" | tr -d ' ')
    
    if [ "$deploy_mode" = "2" ]; then
        echo "Router mode selected."
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_ADDRESS" "0.0.0.0"
        read -p "Public HTTPS port (the port clients use; default: 443): " public_https
        public_https=$(echo "$public_https" | tr -d ' ')
        if [ -z "$public_https" ]; then
            public_https="443"
        fi
        read -p "Local HTTPS port to bind on this host (router forwards here; default: 443): " local_https
        local_https=$(echo "$local_https" | tr -d ' ')
        if [ -z "$local_https" ]; then
            local_https="443"
        fi
        read -p "Public HTTP port (default: 80): " public_http
        public_http=$(echo "$public_http" | tr -d ' ')
        if [ -z "$public_http" ]; then
            public_http="80"
        fi
        read -p "Local HTTP port to bind on this host (default: 80): " local_http
        local_http=$(echo "$local_http" | tr -d ' ')
        if [ -z "$local_http" ]; then
            local_http="80"
        fi
        update_env_var "$ROOT_ENV_FILE" "HTTPS_PORT" "$public_https"
        update_env_var "$ROOT_ENV_FILE" "HTTP_PORT" "$public_http"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTPS_PORT" "$local_https"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTP_PORT" "$local_http"
        echo "   * Public URL: https://$domain:$public_https"
        echo "   * OpenResty will bind to 0.0.0.0 ($local_https/$local_http)"
    else
        echo "Direct mode selected."
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_ADDRESS" "0.0.0.0"
        read -p "HTTPS port (default: 443): " direct_https
        direct_https=$(echo "$direct_https" | tr -d ' ')
        if [ -z "$direct_https" ]; then
            direct_https="443"
        fi
        read -p "HTTP port (default: 80): " direct_http
        direct_http=$(echo "$direct_http" | tr -d ' ')
        if [ -z "$direct_http" ]; then
            direct_http="80"
        fi
        update_env_var "$ROOT_ENV_FILE" "HTTPS_PORT" "$direct_https"
        update_env_var "$ROOT_ENV_FILE" "HTTP_PORT" "$direct_http"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTPS_PORT" "$direct_https"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTP_PORT" "$direct_http"
        echo "   * Server: https://$domain:$direct_https"
        echo "   * Using ports ($direct_https/$direct_http)"
    fi
fi

echo
echo "JWT Issuer (Full/Lite)"
echo "======================"
echo "ISSUER controls which JWT issuer OpenResty accepts:"
echo "  - Leave empty -> Full mode (this gateway handles auth + access)."
echo "  - Set https://<your-full-gateway-domain>/auth -> Lite mode (trust Full-issued JWTs)."
echo "  - In Lite mode, public key sync is automatic from https://<issuer-origin>/.well-known/public-key.pem."
echo "  - Lite mode disables local auth/billing/intents endpoints, but keeps lab/FMU access using those external JWTs."
current_issuer="$(get_env_default "ISSUER" "$ROOT_ENV_FILE")"
if [ -n "$current_issuer" ]; then
    echo "Current ISSUER in .env: $current_issuer"
else
    echo "Current ISSUER in .env: (empty)"
fi
read -p "ISSUER [empty->Full, https://full/auth->Lite]: " issuer_value
issuer_value=$(echo "$issuer_value" | tr -d ' ')
update_env_var "$ROOT_ENV_FILE" "ISSUER" "$issuer_value"
if [ -z "$issuer_value" ]; then
    update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_SERVICES_ENABLED" "true"
    echo "   * ISSUER left empty (Full mode)."
    echo "   * Embedded blockchain-services enabled."
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_URL" ""
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN" ""
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"
    echo "   * LAB_ADMIN_BACKEND_URL left empty (Full mode uses embedded blockchain-services)."
    session_observer_gateway_id="$(get_env_default "SESSION_OBSERVER_GATEWAY_ID" "$ROOT_ENV_FILE")"
    session_observer_signing_secret="$(get_env_default "SESSION_OBSERVER_SIGNING_SECRET" "$ROOT_ENV_FILE")"
    session_observer_credentials_json="$(get_env_default "SESSION_OBSERVER_CREDENTIALS_JSON" "$ROOT_ENV_FILE")"
    if [ -z "$session_observer_gateway_id" ]; then
        session_observer_gateway_id="$(printf '%s' "$domain" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-zA-Z0-9._-')"
    fi
    if [ -z "$session_observer_signing_secret" ]; then
        session_observer_signing_secret="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n')"
    fi
    if [ -z "$session_observer_credentials_json" ] || [ "$session_observer_credentials_json" = "{}" ]; then
        session_observer_credentials_json="{\"${session_observer_gateway_id}\":\"${session_observer_signing_secret}\"}"
    fi
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_GATEWAY_ID" "$session_observer_gateway_id"
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_SIGNING_SECRET" "$session_observer_signing_secret"
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_CREDENTIALS_JSON" "$session_observer_credentials_json"
    access_code_redeemer_credentials_json="$(get_env_default "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON" "$ROOT_ENV_FILE")"
    if [ -z "$access_code_redeemer_credentials_json" ] || [ "$access_code_redeemer_credentials_json" = "{}" ]; then
        access_code_redeemer_credentials_json="{\"${session_observer_gateway_id}\":\"${access_code_redeemer_token}\"}"
    fi
    update_env_var "$ROOT_ENV_FILE" "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON" "$access_code_redeemer_credentials_json"
    update_env_var "$ROOT_ENV_FILE" "ACCESS_AUDIT_URL" ""
    update_env_var "$ROOT_ENV_FILE" "AUTH_SESSION_TICKET_ISSUE_URL" "http://blockchain-services:8080/auth/fmu/session-ticket/issue"
    update_env_var "$ROOT_ENV_FILE" "AUTH_SESSION_TICKET_REDEEM_URL" "http://blockchain-services:8080/auth/fmu/session-ticket/redeem"
    echo "   * Configured a dedicated signed session-observer credential for this Full gateway."
else
    update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_SERVICES_ENABLED" "false"
    echo "   * ISSUER set to: $issuer_value (Lite mode)."
    echo "   * Embedded blockchain-services kept dormant (Lite mode)."
    echo
    echo "Lite /lab-admin Remote Backend"
    echo "=============================="
    echo "Optional. Configure this only if this Lite gateway must publish/update labs on-chain from /lab-manager."
    echo "Leave empty to keep /lab-admin blocked in Lite mode."
    read -p "LAB_ADMIN_BACKEND_URL [empty -> blocked]: " lab_admin_backend_url
    lab_admin_backend_url=$(echo "$lab_admin_backend_url" | tr -d ' ')
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_URL" "$lab_admin_backend_url"
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"
    update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"
    if [ -z "$lab_admin_backend_url" ]; then
        update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN" ""
        echo "   * LAB_ADMIN_BACKEND_URL left empty (/lab-admin remains blocked in Lite mode)."
        echo "   * LAB_ADMIN_BACKEND_TOKEN left empty."
    else
        read -p "LAB_ADMIN_BACKEND_TOKEN [empty -> configure later]: " lab_admin_backend_token
        lab_admin_backend_token=$(echo "$lab_admin_backend_token" | tr -d ' ')
        update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN" "$lab_admin_backend_token"
        echo "   * LAB_ADMIN_BACKEND_URL set to: $lab_admin_backend_url"
        if [ -z "$lab_admin_backend_token" ]; then
            echo "   * LAB_ADMIN_BACKEND_TOKEN left empty (/lab-admin remote calls will fail until it is configured)."
        else
            echo "   * LAB_ADMIN_BACKEND_TOKEN configured."
        fi
    fi
    echo "   * LAB_ADMIN_BACKEND_TOKEN_HEADER set to: X-Lab-Manager-Token"
    echo "   * LAB_ADMIN_BACKEND_ALLOW_INSECURE set to: false"
    echo
    echo "Lite Gateway Trust Bundle"
    echo "========================="
    echo "Import the bundle created on Full with scripts/issue-lite-trust-bundle.sh."
    read -p "Trust bundle path: " lite_trust_bundle
    lite_trust_bundle=$(echo "$lite_trust_bundle" | tr -d '\r')
    if [ -z "$lite_trust_bundle" ] || [ ! -f "$lite_trust_bundle" ]; then
        echo "A Full-issued trust bundle is required in Lite mode." >&2
        exit 1
    fi
    bundle_issuer="$(get_env_default "ISSUER" "$lite_trust_bundle")"
    bundle_redeemer="$(get_env_default "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "$lite_trust_bundle")"
    bundle_audit_url="$(get_env_default "ACCESS_AUDIT_URL" "$lite_trust_bundle")"
    bundle_server_name="$(get_env_default "SERVER_NAME" "$lite_trust_bundle")"
    bundle_gateway_id="$(get_env_default "SESSION_OBSERVER_GATEWAY_ID" "$lite_trust_bundle")"
    bundle_observer_secret="$(get_env_default "SESSION_OBSERVER_SIGNING_SECRET" "$lite_trust_bundle")"
    bundle_guacamole_provisioner_token="$(get_env_default "GUACAMOLE_PROVISIONER_TOKEN" "$lite_trust_bundle")"
    bundle_guacamole_provisioner_token_header="$(get_env_default "GUACAMOLE_PROVISIONER_TOKEN_HEADER" "$lite_trust_bundle")"
    bundle_fmu_gateway_id="$(get_env_default "FMU_GATEWAY_ID" "$lite_trust_bundle")"
    bundle_fmu_audience="$(get_env_default "FMU_JWT_AUDIENCE" "$lite_trust_bundle")"
    bundle_ticket_issue_url="$(get_env_default "AUTH_SESSION_TICKET_ISSUE_URL" "$lite_trust_bundle")"
    bundle_ticket_redeem_url="$(get_env_default "AUTH_SESSION_TICKET_REDEEM_URL" "$lite_trust_bundle")"
    if [ -z "$bundle_issuer" ] || [ -z "$bundle_redeemer" ] || [ -z "$bundle_audit_url" ] \
        || [ -z "$bundle_server_name" ] || [ -z "$bundle_gateway_id" ] || [ -z "$bundle_observer_secret" ] \
        || [ -z "$bundle_guacamole_provisioner_token" ] || [ -z "$bundle_guacamole_provisioner_token_header" ] \
        || [ -z "$bundle_fmu_gateway_id" ] || [ -z "$bundle_fmu_audience" ] \
        || [ -z "$bundle_ticket_issue_url" ] || [ -z "$bundle_ticket_redeem_url" ]; then
        echo "Trust bundle is incomplete or invalid." >&2
        exit 1
    fi
    if [ "$bundle_issuer" != "$issuer_value" ]; then
        echo "Trust bundle ISSUER does not match the configured Full issuer." >&2
        exit 1
    fi
    expected_gateway_id="$(printf '%s' "$domain" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//')"
    if [ "$bundle_server_name" != "$expected_gateway_id" ] \
        || [ "$bundle_gateway_id" != "$expected_gateway_id" ] \
        || [ "$bundle_fmu_gateway_id" != "$expected_gateway_id" ]; then
        echo "Trust bundle gateway identity does not match SERVER_NAME ${expected_gateway_id}." >&2
        exit 1
    fi
    update_env_var "$ROOT_ENV_FILE" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "$bundle_redeemer"
    update_env_var "$ROOT_ENV_FILE" "ACCESS_AUDIT_URL" "$bundle_audit_url"
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_GATEWAY_ID" "$bundle_gateway_id"
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_SIGNING_SECRET" "$bundle_observer_secret"
    update_env_var "$ROOT_ENV_FILE" "GUACAMOLE_PROVISIONER_TOKEN" "$bundle_guacamole_provisioner_token"
    update_env_var "$ROOT_ENV_FILE" "GUACAMOLE_PROVISIONER_TOKEN_HEADER" "$bundle_guacamole_provisioner_token_header"
    update_env_var "$ROOT_ENV_FILE" "FMU_GATEWAY_ID" "$bundle_fmu_gateway_id"
    update_env_var "$ROOT_ENV_FILE" "AUTH_SESSION_TICKET_ISSUE_URL" "$bundle_ticket_issue_url"
    update_env_var "$ROOT_ENV_FILE" "AUTH_SESSION_TICKET_REDEEM_URL" "$bundle_ticket_redeem_url"
    update_env_var "$ROOT_ENV_FILE" "SESSION_OBSERVER_CREDENTIALS_JSON" "{}"
    echo "   * Imported redeem, session-observation and Guacamole-provisioner credentials for ${bundle_gateway_id}."
fi
echo

echo
echo "FMU Runner Integration"
echo "======================"
echo "Controls whether /fmu and FMU AAS sync routes are active on this gateway."
echo "When disabled, OpenResty starts without requiring the fmu-runner container and those routes return 503."
echo "FMU runner is optional and disabled unless FMU_RUNNER_ENABLED is explicitly enabled."
current_fmu_runner_enabled="$(get_env_default "FMU_RUNNER_ENABLED" "$ROOT_ENV_FILE")"
if [ -z "$current_fmu_runner_enabled" ]; then
    current_fmu_runner_enabled="false"
else
    case "${current_fmu_runner_enabled,,}" in
        false|0|no)
            current_fmu_runner_enabled="false"
            ;;
        *)
            current_fmu_runner_enabled="true"
            ;;
    esac
fi
if [ "$current_fmu_runner_enabled" = "true" ]; then
    fmu_prompt="Y/n"
else
    fmu_prompt="y/N"
fi
read -p "Enable FMU runner integration? [$fmu_prompt]: " enable_fmu_runner
enable_fmu_runner=$(echo "$enable_fmu_runner" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
if [ -z "$enable_fmu_runner" ]; then
    fmu_runner_enabled="$current_fmu_runner_enabled"
elif [ "$enable_fmu_runner" = "y" ] || [ "$enable_fmu_runner" = "yes" ] || [ "$enable_fmu_runner" = "true" ] || [ "$enable_fmu_runner" = "1" ]; then
    fmu_runner_enabled="true"
else
    fmu_runner_enabled="false"
fi
update_env_var "$ROOT_ENV_FILE" "FMU_RUNNER_ENABLED" "$fmu_runner_enabled"
if [ "$fmu_runner_enabled" = "true" ]; then
    echo "   * FMU runner enabled. /fmu routes are active."
    echo "   * Compose starts the Station-only facade. Use --profile fmu-local-dev only for isolated local FMU development."
else
    echo "   * FMU runner disabled. Startup will use '--scale fmu-runner=0'."
fi
echo

echo
echo "AAS Support (Asset Administration Shell)"
echo "========================================="
if [ -n "$issuer_value" ]; then
    echo "Lite Gateway detected — AAS is only available on Full Gateway instances. Skipping."
    update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
    update_env_var "$ROOT_ENV_FILE" "AAS_ALLOWED_HOSTS" ""
    update_env_var "$ROOT_ENV_FILE" "AAS_SERVICE_TOKEN" ""
else
    echo "AAS enables publishing Digital Twin descriptions (IDTA 02006) for FMUs and physical labs."
    echo "  1) Bundled BaSyx  — Deploy the included BaSyx AAS Server container (recommended)"
    echo "  2) External server — Connect to an existing AAS server (BaSyx, NOVAAS, etc.)"
    echo "  3) None           — Skip AAS support"
    read -p "AAS server [1/2/3] (default: 1): " aas_option
    aas_option=$(echo "$aas_option" | tr -d ' ')
    case "$aas_option" in
        2)
            echo "External AAS server selected."
            read -p "External AAS API base URL (HTTPS only, e.g. https://my-aas.example.com): " external_aas_url
            external_aas_url=$(echo "$external_aas_url" | tr -d ' ')
            if [ -z "$external_aas_url" ]; then
                echo "No URL provided. AAS support disabled."
                update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
            else
                echo "   * External AAS server: $external_aas_url"
                echo "   * Bundled basyx-aas-server / basyx-mongo containers will NOT be started."
                update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" "$external_aas_url"
                read -p "Exact allowlisted AAS hostname (without port, e.g. my-aas.example.com): " aas_allowed_hosts
                aas_allowed_hosts=$(echo "$aas_allowed_hosts" | tr -d ' ')
                if [ -z "$aas_allowed_hosts" ]; then
                    aas_allowed_hosts="$existing_aas_allowed_hosts"
                fi
                read -s -p "Dedicated AAS service token (leave empty to generate): " aas_service_token
                echo
                if [ -z "$aas_service_token" ]; then
                    aas_service_token="$existing_aas_service_token"
                fi
                if [ -z "$aas_service_token" ] || is_placeholder_secret "$aas_service_token"; then
                    aas_service_token="aas_$(openssl rand -hex 32 2>/dev/null || echo ${RANDOM}${RANDOM}${RANDOM}${RANDOM})"
                fi
                update_env_var "$ROOT_ENV_FILE" "AAS_ALLOWED_HOSTS" "$aas_allowed_hosts"
                update_env_var "$ROOT_ENV_FILE" "AAS_SERVICE_TOKEN" "$aas_service_token"
                update_env_var "$ROOT_ENV_FILE" "AAS_SERVICE_TOKEN_HEADER" "Authorization"
            fi
            ;;
        3)
            echo "AAS support disabled."
            update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
            update_env_var "$ROOT_ENV_FILE" "AAS_ALLOWED_HOSTS" ""
            update_env_var "$ROOT_ENV_FILE" "AAS_SERVICE_TOKEN" ""
            ;;
        *)
            echo "Bundled BaSyx selected."
            update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
            update_env_var "$ROOT_ENV_FILE" "AAS_ALLOWED_HOSTS" ""
            update_env_var "$ROOT_ENV_FILE" "AAS_SERVICE_TOKEN" ""
            aas_bundled=true
            ;;
    esac
fi
echo

echo
echo "Remote Access (Cloudflare Tunnel)"
echo "================================="
read -p "Enable Cloudflare Tunnel to expose the gateway without opening inbound ports? (y/N): " enable_cf
enable_cf=$(echo "$enable_cf" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
if [ "$enable_cf" = "y" ] || [ "$enable_cf" = "yes" ]; then
    cf_enabled=true
    read -p "Cloudflare Tunnel token (leave empty to use a Quick Tunnel): " cf_token
    cf_token=$(echo "$cf_token" | tr -d ' ')
    if [ -n "$cf_token" ]; then
        update_env_var "$ROOT_ENV_FILE" "CLOUDFLARE_TUNNEL_TOKEN" "$cf_token"
    else
        update_env_var "$ROOT_ENV_FILE" "CLOUDFLARE_TUNNEL_TOKEN" ""
    fi
    if [ "$domain" = "localhost" ]; then
        echo "Cloudflare enabled: switching to standard ports (443/80) for a cleaner public URL."
        update_env_var "$ROOT_ENV_FILE" "HTTPS_PORT" "443"
        update_env_var "$ROOT_ENV_FILE" "HTTP_PORT" "80"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTPS_PORT" "443"
        update_env_var "$ROOT_ENV_FILE" "OPENRESTY_BIND_HTTP_PORT" "80"
    fi
fi

configured_https_port="$(get_env_default "HTTPS_PORT" "$ROOT_ENV_FILE")"
gateway_public_origin="https://${domain}"
if [ "${configured_https_port:-443}" != "443" ]; then
    gateway_public_origin="${gateway_public_origin}:${configured_https_port}"
fi
expected_fmu_audience="${gateway_public_origin}/fmu"
if [ -n "$issuer_value" ] && [ "${bundle_fmu_audience:-}" != "$expected_fmu_audience" ]; then
    echo "Trust bundle FMU audience does not match this Lite gateway public URL (${expected_fmu_audience})." >&2
    exit 1
fi
update_env_var "$ROOT_ENV_FILE" "FMU_JWT_AUDIENCE" "${gateway_public_origin}/fmu"
echo "   * FMU JWT audience: ${expected_fmu_audience}"

# Repair modes after all generated values have been written.  This is also
# executed when the operator chooses not to start Docker services.
secure_gateway_state

# Docker Compose local secrets must be backed by files when a read-only service
# consumes them. Keep the generated files synchronized with the gateway env
# after all interactive configuration has been written.
sync_compose_secrets

echo
echo "Ops Worker configuration"
echo "------------------------"
echo "By default the stack mounts ops-worker/hosts.empty.json."
echo "To use your own hosts file, set OPS_CONFIG_PATH=./ops-worker/hosts.json before running docker compose."
echo
echo "SSL Certificates"
echo "================"

mkdir -p certs
mkdir -p blockchain-data
mkdir -p lab-content
mkdir -p fmu-data
mkdir -p fmu-proxy-runtime/binaries/linux64
mkdir -p fmu-proxy-runtime/binaries/win64
mkdir -p fmu-proxy-runtime/binaries/darwin64
mkdir -p ops-data/guac-revocation-spool
chmod 700 certs 2>/dev/null || true
chmod 700 blockchain-data 2>/dev/null || true
chmod 755 lab-content 2>/dev/null || true
chmod 755 fmu-data 2>/dev/null || true
chmod 755 fmu-proxy-runtime 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/linux64 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/win64 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/darwin64 2>/dev/null || true
chmod 700 ops-data/guac-revocation-spool 2>/dev/null || true
secure_gateway_state

echo
echo "Host User Mapping"
echo "================="
host_user="${SUDO_USER:-}"
if [ -z "$host_user" ]; then
    host_user="$(id -un)"
fi
host_uid="$(id -u "$host_user" 2>/dev/null || echo "")"
host_gid="$(id -g "$host_user" 2>/dev/null || echo "")"
if [ -n "$host_uid" ] && [ -n "$host_gid" ]; then
    update_env_var "$ROOT_ENV_FILE" "HOST_UID" "$host_uid"
    update_env_var "$ROOT_ENV_FILE" "HOST_GID" "$host_gid"
    echo "Configured HOST_UID/HOST_GID to ${host_uid}:${host_gid}"

    # Align permissions so containers can write to bind mounts without manual chmod.
    if command -v chown >/dev/null 2>&1; then
        if chown -R "${host_uid}:${host_gid}" certs blockchain-data lab-content 2>/dev/null; then
            echo "Adjusted ownership of certs/, blockchain-data/, and lab-content/ to ${host_uid}:${host_gid}"
        else
            echo "Warning: Unable to change ownership of certs/, blockchain-data/, or lab-content/. Run chown manually if needed." >&2
        fi
    fi
else
    echo "Warning: Unable to detect host UID/GID; using defaults."
fi

if [ -f "certs/fullchain.pem" ] && [ -f "certs/privkey.pem" ]; then
    echo "SSL certificates found in certs/ - they will be used."
else
    echo "No SSL certificates in certs/ - OpenResty will auto-generate self-signed certs at startup."
    if [ "$domain" != "localhost" ]; then
        echo
        echo "For production, consider adding valid certificates:"
        echo "  * certs/fullchain.pem (certificate chain)"
        echo "  * certs/privkey.pem (private key)"
        echo "Sources: Let's Encrypt (certbot), your CA, or cloud provider."
    fi
fi

echo
echo "JWT Signing Keys"
echo "================"
echo "blockchain-services will generate the key if missing (volume ./blockchain-data)."
if [ -f "blockchain-data/keys/private_key.pem" ]; then
    echo "private_key.pem already exists in blockchain-data/keys/ (it will be reused)."
else
    echo "No private_key.pem in blockchain-data/keys/; the container will create a new one at startup."
fi

echo
echo "Certbot (Let's Encrypt) - optional automation"
echo "============================================"
read -p "Domains for TLS (comma-separated, leave empty to skip ACME): " cb_domains
cb_domains=$(echo "$cb_domains" | tr -d ' ')
read -p "Email for ACME (leave empty to skip ACME): " cb_email
cb_email=$(echo "$cb_email" | tr -d ' ')
if [ -n "$cb_domains" ] && [ -n "$cb_email" ]; then
    update_env_var "$ROOT_ENV_FILE" "CERTBOT_DOMAINS" "$cb_domains"
    update_env_var "$ROOT_ENV_FILE" "CERTBOT_EMAIL" "$cb_email"
    certbot_enabled=true
    echo "Configured CERTBOT_DOMAINS and CERTBOT_EMAIL in .env"
else
    echo "Skipped certbot configuration (ACME). Self-signed certificates will be auto-rotated in-container every ~87 days."
fi
if [ "$certbot_enabled" != true ]; then
    certbot_domains=$(get_env_default "CERTBOT_DOMAINS" "$ROOT_ENV_FILE")
    certbot_email=$(get_env_default "CERTBOT_EMAIL" "$ROOT_ENV_FILE")
    if [ -n "$certbot_domains" ] && [ -n "$certbot_email" ]; then
        certbot_enabled=true
    fi
fi

echo
echo "Blockchain Services Configuration"
echo "================================="

echo
# Provider registration enabled by default (non-interactive).
update_env_var "$BLOCKCHAIN_ENV_FILE" "FEATURES_PROVIDERS_ENABLED" "true"
update_env_var "$BLOCKCHAIN_ENV_FILE" "FEATURES_PROVIDERS_REGISTRATION_ENABLED" "true"

# Use CONTRACT_ADDRESS from blockchain-services/.env (no prompt)
contract_default=$(get_env_default "CONTRACT_ADDRESS" "$BLOCKCHAIN_ENV_FILE")
if [ -n "$contract_default" ]; then
    update_env_var "$BLOCKCHAIN_ENV_FILE" "CONTRACT_ADDRESS" "$contract_default"
fi

sepolia_default=$(get_env_default "ETHEREUM_SEPOLIA_RPC_URL" "$BLOCKCHAIN_ENV_FILE")
read -p "Comma-separated Sepolia RPC URLs [${sepolia_default:-https://ethereum-sepolia-rpc.publicnode.com,https://0xrpc.io/sep,https://ethereum-sepolia-public.nodies.app}]: " sepolia_rpc
sepolia_rpc=${sepolia_rpc:-$sepolia_default}
if [ -n "$sepolia_rpc" ]; then
    update_env_var "$BLOCKCHAIN_ENV_FILE" "ETHEREUM_SEPOLIA_RPC_URL" "$sepolia_rpc"
fi

allowed_origins_default=$(get_env_default "ALLOWED_ORIGINS" "$BLOCKCHAIN_ENV_FILE")
read -p "Allowed origins for CORS [${allowed_origins_default:-https://marketplace-decentralabs.vercel.app}]: " allowed_origins
allowed_origins=${allowed_origins:-${allowed_origins_default:-https://marketplace-decentralabs.vercel.app}}
if [ -n "$allowed_origins" ]; then
    update_env_var "$BLOCKCHAIN_ENV_FILE" "ALLOWED_ORIGINS" "$allowed_origins"
fi

public_key_url_default=$(get_env_default "MARKETPLACE_PUBLIC_KEY_URL" "$BLOCKCHAIN_ENV_FILE")
read -p "Marketplace public key URL [${public_key_url_default:-https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem}]: " marketplace_pk
marketplace_pk=${marketplace_pk:-$public_key_url_default}
if [ -n "$marketplace_pk" ]; then
    update_env_var "$BLOCKCHAIN_ENV_FILE" "MARKETPLACE_PUBLIC_KEY_URL" "$marketplace_pk"
fi

if [ "$cf_enabled" = true ]; then
    if [ -n "$cf_token" ]; then
        cf_profile="cloudflare-token"
        cf_service="cloudflared-token"
    else
        cf_profile="cloudflare"
        cf_service="cloudflared"
    fi
    compose_profiles="--profile $cf_profile"
fi
if [ "$certbot_enabled" = true ]; then
    if [ -n "$compose_profiles" ]; then
        compose_profiles="$compose_profiles --profile certbot"
    else
        compose_profiles="--profile certbot"
    fi
fi
if [ "$aas_bundled" = true ]; then
    if [ -n "$compose_profiles" ]; then
        compose_profiles="$compose_profiles --profile aas"
    else
        compose_profiles="--profile aas"
    fi
fi

if [ "$fmu_runner_enabled" = "true" ]; then
    if [ -n "$compose_profiles" ]; then
        compose_profiles="$compose_profiles --profile fmu-runner"
    else
        compose_profiles="--profile fmu-runner"
    fi
fi

# Build final compose command
compose_full="$compose_cmd"
if [ -n "$compose_files" ]; then
    compose_full="$compose_full $compose_files"
fi
if [ -n "$compose_profiles" ]; then
    compose_full="$compose_full $compose_profiles"
fi
compose_up_args="up -d"
if [ "$fmu_runner_enabled" != "true" ]; then
    compose_up_args="up -d --scale fmu-runner=0"
fi

echo
echo "Institutional Wallet Reminder"
echo "-----------------------------"
echo "This script does not create wallets automatically."
echo "After the stack is running, create or import the institutional wallet"
echo "using the blockchain-services web console (or the /wallet API) and then"
echo "update INSTITUTIONAL_WALLET_ADDRESS / PASSWORD in:"
echo "  - blockchain-services/.env"
echo "Wallet data is stored in ./blockchain-data (already created)."
echo "FMU proxy runtime binaries must be copied into ./fmu-proxy-runtime/binaries/{linux64,win64,darwin64} before proxy downloads will work."

echo
echo "Next Steps"
echo "=========="
echo "1. Review and customize .env file if needed"
echo "2. Ensure SSL certificates are in place"
echo "3. Configure blockchain settings in blockchain-services/.env as needed"
echo "4. Run: $compose_full $compose_up_args"
if [ "$cf_enabled" = true ]; then
    echo "5. Cloudflare tunnel: check '$compose_full logs ${cf_service:-cloudflared}' for the public hostname (or your configured tunnel token domain)."
fi
https_port=$(get_env_default "HTTPS_PORT" "$ROOT_ENV_FILE")
http_port=$(get_env_default "HTTP_PORT" "$ROOT_ENV_FILE")
if [ "$domain" = "localhost" ]; then
    echo "Access: https://localhost:${https_port:-8443} (HTTP: ${http_port:-8081})"
else
    echo "Access: https://$domain"
fi
if [ "$domain" = "localhost" ]; then
    token_host="https://localhost"
    if [ "${https_port:-8443}" != "443" ]; then
        token_host="${token_host}:${https_port:-8443}"
    fi
else
    token_host="https://$domain"
    if [ "${https_port:-443}" != "443" ]; then
        token_host="${token_host}:${https_port}"
    fi
fi
echo "   * Admin dashboard: ${token_host}/wallet-dashboard (login required)"
echo "   * Lab Manager: ${token_host}/lab-manager (login required)"
echo "   * Guacamole: /guacamole/"
echo "   * Blockchain Services API: /auth"
echo

# Ask if user wants to start services
read -p "Do you want to start the services now? (Y/n): " start_services
case "$start_services" in
    [Nn]|[Nn][Oo])
        echo "Configuration complete!"
        echo
        echo "Next steps:"
        echo "1. Configure blockchain settings in blockchain-services/.env (CONTRACT_ADDRESS, WALLET_ADDRESS, INSTITUTIONAL_WALLET_*)"
        echo "2. Run: $compose_full $compose_up_args"
        echo "3. Access your services"
        if [ "$cf_enabled" = true ]; then
            echo "4. Cloudflare tunnel hostname: $compose_full logs ${cf_service:-cloudflared}"
        fi
        echo
        echo "For more information, see README.md"
        echo "Setup complete!"
        exit 0
        ;;
    *)
        ;;
esac

echo
echo "Building and starting services..."
echo "This may take several minutes on first run..."

$compose_full down --remove-orphans
if ! $compose_full build --no-cache; then
    echo "Failed to build services. Check the error messages above." >&2
    exit 1
fi

if $compose_full $compose_up_args; then
    echo
    echo "Services started successfully!"
if [ "$domain" = "localhost" ]; then
    echo "Access your lab at: https://localhost:${https_port:-8443}"
else
    echo "Access your lab at: https://$domain"
fi
if [ "$domain" = "localhost" ]; then
    token_host="https://localhost"
    if [ "${https_port:-8443}" != "443" ]; then
        token_host="${token_host}:${https_port:-8443}"
    fi
else
    token_host="https://$domain"
    if [ "${https_port:-443}" != "443" ]; then
        token_host="${token_host}:${https_port}"
    fi
fi
echo "   * Admin dashboard: ${token_host}/wallet-dashboard (login required)"
echo "   * Lab Manager: ${token_host}/lab-manager (login required)"
echo "   * Guacamole: /guacamole/ ($guac_admin_user / $guac_admin_pass)"
echo "   * Blockchain Services API: /auth"
    if [ "$cf_enabled" = true ]; then
        echo "   * Cloudflare tunnel logs (hostname): $compose_full logs ${cf_service:-cloudflared}"
    fi
    echo
    echo "To check status: $compose_full ps"
    echo "To view logs: $compose_full logs -f"
    echo
    echo "Configuration:"
    echo "   Environment: .env"
    echo "   Certificates: certs/"
    echo "   Blockchain Services Config: blockchain-services/src/main/resources/"
    echo
    echo "Full version deployment complete!"
    echo "Your blockchain-based authentication system is now running."
else
    echo "Failed to start services. Check the error messages above." >&2
    exit 1
fi

echo
echo "For more information, see README.md"
echo "Setup complete!"
