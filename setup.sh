#!/bin/bash

# =================================================================
# DecentraLabs Gateway - Full Version Setup Script (Linux/macOS)
# Complete blockchain-based authentication system with blockchain-services
# =================================================================

set -euo pipefail

ROOT_ENV_FILE=".env"
BLOCKCHAIN_ENV_FILE="blockchain-services/.env"
compose_cmd="docker compose"
compose_files=""
compose_profiles=""
cf_enabled=false
certbot_enabled=false
aas_bundled=false
fmu_runner_enabled=true
existing_mysql_root_password=""
existing_mysql_password=""
db_credentials_changed=false
reset_mysql_volume=false
mysql_volume_name=""

echo "DecentraLabs Gateway - Full Version Setup"
echo "=========================================="
echo

update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"

    if grep -qE "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >> "$file"
    fi
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

detect_mysql_volume() {
    local project_name="${COMPOSE_PROJECT_NAME:-}"
    local volume_name=""

    if [ -z "$project_name" ]; then
        project_name="$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
    fi

    volume_name="$(docker volume ls -q \
        --filter "label=com.docker.compose.project=${project_name}" \
        --filter "label=com.docker.compose.volume=mysql_data" | head -n 1)"

    if [ -z "$volume_name" ] && docker volume inspect "${project_name}_mysql_data" >/dev/null 2>&1; then
        volume_name="${project_name}_mysql_data"
    fi

    echo "$volume_name"
}

update_env_in_all() {
    local key="$1"
    local value="$2"
    update_env_var "$ROOT_ENV_FILE" "$key" "$value"
    if [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
        update_env_var "$BLOCKCHAIN_ENV_FILE" "$key" "$value"
    fi
}

update_env_blockchain_only() {
    local key="$1"
    local value="$2"
    if [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
        update_env_var "$BLOCKCHAIN_ENV_FILE" "$key" "$value"
    fi
}

# Check prerequisites
echo "Checking prerequisites..."
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

if ! command -v git &> /dev/null; then
    echo "Git is required to initialize blockchain-services."
    exit 1
fi

echo "Docker, Docker Compose, and Git are available"
echo

echo "Ensuring blockchain-services submodule is present..."
git submodule update --init --recursive blockchain-services
echo "blockchain-services submodule ready."
echo

existing_mysql_root_password="$(get_env_default "MYSQL_ROOT_PASSWORD" "$ROOT_ENV_FILE")"
existing_mysql_password="$(get_env_default "MYSQL_PASSWORD" "$ROOT_ENV_FILE")"

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
echo

# Database Passwords Configuration
echo
echo "Database Passwords"
echo "=================="
echo "Enter database passwords (leave empty for auto-generated):"
read -p "MySQL root password: " mysql_root_password
read -p "Guacamole database password: " mysql_password

if [ -z "$mysql_root_password" ]; then
    if [ -n "$existing_mysql_root_password" ] && ! is_placeholder_secret "$existing_mysql_root_password"; then
        mysql_root_password="$existing_mysql_root_password"
        echo "Reusing existing MySQL root password from .env"
    else
        mysql_root_password="R00t_$(openssl rand -hex 16 2>/dev/null || echo P@ss_${RANDOM}_$(date +%s))"
        echo "Generated root password: $mysql_root_password"
    fi
fi

if [ -z "$mysql_password" ]; then
    if [ -n "$existing_mysql_password" ] && ! is_placeholder_secret "$existing_mysql_password"; then
        mysql_password="$existing_mysql_password"
        echo "Reusing existing Guacamole DB password from .env"
    else
        mysql_password="Gu@c_$(openssl rand -hex 16 2>/dev/null || echo ${RANDOM}_$(date +%s))"
        echo "Generated database password: $mysql_password"
    fi
fi

# Update passwords only in gateway env (.env). Standalone blockchain-services
# uses BCHAIN_MYSQL_* keys in its own .env.
update_env_var "$ROOT_ENV_FILE" "MYSQL_ROOT_PASSWORD" "$mysql_root_password"
update_env_var "$ROOT_ENV_FILE" "MYSQL_PASSWORD" "$mysql_password"

if [ "$mysql_root_password" != "$existing_mysql_root_password" ] || [ "$mysql_password" != "$existing_mysql_password" ]; then
    db_credentials_changed=true
fi

mysql_volume_name="$(detect_mysql_volume)"
if [ -n "$mysql_volume_name" ] && [ "$db_credentials_changed" = true ]; then
    echo
    echo "Detected existing MySQL volume: ${mysql_volume_name}"
    echo "Database credentials changed in .env, so startup can fail with Access denied (1045)."
    read -p "Reset MySQL volume now to apply new credentials? This removes MySQL data. (y/N): " reset_mysql_input
    reset_mysql_input="$(echo "$reset_mysql_input" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
    if [ "$reset_mysql_input" = "y" ] || [ "$reset_mysql_input" = "yes" ]; then
        reset_mysql_volume=true
        echo "MySQL volume will be reset before startup."
    else
        echo "Keeping existing MySQL volume. If startup fails, run: docker compose down -v"
    fi
fi

echo
echo "IMPORTANT: Save these passwords securely!"
echo "   Root password: $mysql_root_password"
echo "   Database password: $mysql_password"
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

update_env_in_all "ADMIN_ACCESS_TOKEN" "$access_token"
update_env_in_all "ADMIN_ACCESS_TOKEN_HEADER" "X-Access-Token"
update_env_in_all "ADMIN_ACCESS_TOKEN_COOKIE" "access_token"
update_env_blockchain_only "ADMIN_ACCESS_TOKEN_REQUIRED" "true"
update_env_blockchain_only "ADMIN_DASHBOARD_LOCAL_ONLY" "true"

echo
echo "Wallet Dashboard Access Scope"
echo "============================="
echo "Choose how /wallet-dashboard and wallet/billing admin routes are exposed:"
echo "  1) Localhost only (recommended)"
echo "  2) Private networks + admin access token"
read -p "Choose [1/2] (default: 1): " dashboard_access_scope
dashboard_access_scope=$(echo "$dashboard_access_scope" | tr -d ' ')

if [ "$dashboard_access_scope" = "2" ]; then
    update_env_blockchain_only "SECURITY_ALLOW_PRIVATE_NETWORKS" "true"
    update_env_blockchain_only "ADMIN_DASHBOARD_ALLOW_PRIVATE" "true"
    update_env_blockchain_only "ADMIN_DASHBOARD_LOCAL_ONLY" "false"
    read -p "Allowed private CIDRs (comma-separated, leave empty for any private range): " admin_allowed_cidrs
    admin_allowed_cidrs=$(echo "$admin_allowed_cidrs" | sed 's/[[:space:]]//g')
    update_env_blockchain_only "ADMIN_ALLOWED_CIDRS" "$admin_allowed_cidrs"
    echo "Configured wallet dashboard access for private networks protected by ADMIN_ACCESS_TOKEN."
else
    update_env_blockchain_only "SECURITY_ALLOW_PRIVATE_NETWORKS" "false"
    update_env_blockchain_only "ADMIN_DASHBOARD_ALLOW_PRIVATE" "false"
    update_env_blockchain_only "ADMIN_DASHBOARD_LOCAL_ONLY" "true"
    update_env_blockchain_only "ADMIN_ALLOWED_CIDRS" ""
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
    echo "   * ISSUER left empty (Full mode)."
else
    echo "   * ISSUER set to: $issuer_value (Lite mode)."
fi
echo

echo
echo "FMU Runner Integration"
echo "======================"
echo "Controls whether /fmu and FMU AAS sync routes are active on this gateway."
echo "When disabled, OpenResty starts without requiring the fmu-runner container and those routes return 503."
current_fmu_runner_enabled="$(get_env_default "FMU_RUNNER_ENABLED" "$ROOT_ENV_FILE")"
if [ -z "$current_fmu_runner_enabled" ]; then
    if [ -n "$issuer_value" ]; then
        current_fmu_runner_enabled="false"
    else
        current_fmu_runner_enabled="true"
    fi
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
            read -p "External AAS API base URL (e.g. http://192.168.1.10:8081 or https://my-aas.example.com): " external_aas_url
            external_aas_url=$(echo "$external_aas_url" | tr -d ' ')
            if [ -z "$external_aas_url" ]; then
                echo "No URL provided. AAS support disabled."
                update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
            else
                echo "   * External AAS server: $external_aas_url"
                echo "   * Bundled basyx-aas-server / basyx-mongo containers will NOT be started."
                update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" "$external_aas_url"
            fi
            ;;
        3)
            echo "AAS support disabled."
            update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
            ;;
        *)
            echo "Bundled BaSyx selected."
            update_env_var "$ROOT_ENV_FILE" "BASYX_AAS_URL" ""
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
mkdir -p fmu-data
mkdir -p fmu-proxy-runtime/binaries/linux64
mkdir -p fmu-proxy-runtime/binaries/win64
mkdir -p fmu-proxy-runtime/binaries/darwin64
chmod 700 certs 2>/dev/null || true
chmod 700 blockchain-data 2>/dev/null || true
chmod 755 fmu-data 2>/dev/null || true
chmod 755 fmu-proxy-runtime 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/linux64 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/win64 2>/dev/null || true
chmod 755 fmu-proxy-runtime/binaries/darwin64 2>/dev/null || true

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
        if chown -R "${host_uid}:${host_gid}" certs blockchain-data 2>/dev/null; then
            echo "Adjusted ownership of certs/ and blockchain-data/ to ${host_uid}:${host_gid}"
        else
            echo "Warning: Unable to change ownership of certs/ or blockchain-data/. Run chown manually if needed." >&2
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
echo "blockchain-services will generate the key if missing (volume ./certs)."
if [ -f "certs/private_key.pem" ]; then
    echo "private_key.pem already exists in certs/ (it will be reused)."
else
    echo "No private_key.pem in certs/; the container will create a new one at startup."
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
echo "3. Configure blockchain settings in blockchain-services/.env is needed"
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
echo "   * Admin access token cookie: ${token_host}/wallet-dashboard?token=${access_token}"
echo "   * Lab Manager token cookie: ${token_host}/lab-manager?token=${lab_manager_token}"
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

set +e
if [ "$reset_mysql_volume" = true ]; then
    $compose_full down --remove-orphans -v
else
    $compose_full down --remove-orphans
fi
$compose_full build --no-cache
$compose_full $compose_up_args
compose_result=$?
set -e

if [ $compose_result -eq 0 ]; then
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
echo "   * Admin access token cookie: ${token_host}/wallet-dashboard?token=${access_token}"
echo "   * Lab Manager token cookie: ${token_host}/lab-manager?token=${lab_manager_token}"
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
    echo "Failed to start services. Check the error messages above."
    if [ -n "$mysql_volume_name" ] && [ "$db_credentials_changed" = true ] && [ "$reset_mysql_volume" != true ]; then
        echo "Hint: Existing MySQL volume uses old credentials. Run: $compose_full down -v"
    fi
fi

echo
echo "For more information, see README.md"
echo "Setup complete!"
