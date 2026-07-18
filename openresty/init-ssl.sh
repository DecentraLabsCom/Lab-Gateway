#!/bin/sh
# =================================================================
# OpenResty SSL Certificate Initialization Script
# Handles SSL/TLS certificates for HTTPS. JWT keys are managed by
# blockchain-services entrypoint separately.
# =================================================================

SSL_DIR="/etc/ssl/private"
CERT_FILE="$SSL_DIR/fullchain.pem"
KEY_FILE="$SSL_DIR/privkey.pem"
TEMP_SSL_DIR="/tmp/ssl"
RENEW_THRESHOLD_SECONDS=$((30 * 24 * 3600))  # 30 days (ACME renewal threshold)
SELF_SIGNED_RENEW_THRESHOLD=$((10 * 24 * 3600))  # 10 days (self-signed regeneration threshold)
SELF_SIGNED_MARKER="$SSL_DIR/.selfsigned_issued"
SELF_SIGNED_MAX_AGE_SECONDS=$((85 * 24 * 3600))  # 85 days (rotate before 90-day expiry)
CERTBOT_WEBROOT="/var/www/certbot"

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

echo "=== OpenResty SSL Certificate Check ==="
echo "Certificate: $CERT_FILE"
echo "Private Key: $KEY_FILE"

# Create SSL directory if it doesn't exist and make it traversable by OpenResty workers
mkdir -p "$SSL_DIR"
chmod 755 "$SSL_DIR" 2>/dev/null || true

trim() {
    echo "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

set_ssl_permissions() {
    chmod 755 "$SSL_DIR" 2>/dev/null || true
    chmod 644 "$CERT_FILE" 2>/dev/null || true
    if grep -q '^openresty:' /etc/group 2>/dev/null; then
        chgrp openresty "$KEY_FILE" 2>/dev/null || true
        chmod 640 "$KEY_FILE" 2>/dev/null || true
    else
        chmod 644 "$KEY_FILE" 2>/dev/null || true
    fi
}

build_local_issuer() {
    local_name="$(trim "${SERVER_NAME:-localhost}")"
    local_port="$(trim "${HTTPS_PORT:-443}")"
    if [ -z "$local_name" ]; then
        local_name="localhost"
    fi
    if [ -n "$local_port" ] && [ "$local_port" != "443" ]; then
        echo "https://${local_name}:${local_port}/auth"
    else
        echo "https://${local_name}/auth"
    fi
}

build_key_url_from_issuer() {
    issuer_raw="$(trim "$1")"
    issuer_no_slash="$(echo "$issuer_raw" | sed 's:/*$::')"
    origin="$(echo "$issuer_no_slash" | sed -n 's#^\(https\?://[^/]*\).*$#\1#p')"
    if [ -z "$origin" ]; then
        return 1
    fi
    echo "${origin}/.well-known/public-key.pem"
}

sync_jwt_public_key_from_issuer() {
    target_issuer="$1"
    key_url="$(build_key_url_from_issuer "$target_issuer" 2>/dev/null || true)"
    if [ -z "$key_url" ]; then
        echo "Invalid issuer URL for key sync: '$target_issuer'"
        return 1
    fi

    tmp_key="${JWT_PUBLIC_KEY}.download"
    echo "Syncing JWT public key from: $key_url"
    if ! curl -fsSL --connect-timeout 10 --max-time 20 "$key_url" -o "$tmp_key"; then
        echo "Failed to download JWT public key from $key_url"
        rm -f "$tmp_key"
        return 1
    fi

    if ! grep -q "BEGIN PUBLIC KEY" "$tmp_key"; then
        echo "Downloaded file is not a PEM public key"
        rm -f "$tmp_key"
        return 1
    fi

    if ! openssl pkey -pubin -in "$tmp_key" -noout >/dev/null 2>&1; then
        echo "Downloaded PEM public key is invalid"
        rm -f "$tmp_key"
        return 1
    fi

    if [ -f "$JWT_PUBLIC_KEY" ] && cmp -s "$tmp_key" "$JWT_PUBLIC_KEY"; then
        rm -f "$tmp_key"
        echo "JWT public key already up-to-date"
        return 0
    fi

    if [ -f "$JWT_PUBLIC_KEY" ]; then
        atomic_copy "$JWT_PUBLIC_KEY" "$JWT_PREVIOUS_PUBLIC_KEY"
        date +%s > "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || true
    fi
    mv "$tmp_key" "$JWT_PUBLIC_KEY"
    chmod 644 "$JWT_PUBLIC_KEY"
    atomic_copy "$JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"
    echo "JWT public key updated from issuer"
    return 10
}

atomic_copy() {
    source_path="$1"
    target_path="$2"
    target_tmp="${target_path}.tmp.$$"
    if ! cp "$source_path" "$target_tmp"; then
        rm -f "$target_tmp"
        return 1
    fi
    chmod 644 "$target_tmp" 2>/dev/null || true
    mv -f "$target_tmp" "$target_path"
}

is_valid_public_key() {
    [ -f "$1" ] && grep -q "BEGIN PUBLIC KEY" "$1" \
        && openssl pkey -pubin -in "$1" -noout >/dev/null 2>&1
}

generate_self_signed() {
    echo "SSL certificates missing or expiring - generating self-signed certificates for development"
    mkdir -p "$TEMP_SSL_DIR"
    cat > "$TEMP_SSL_DIR/openssl.conf" << EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = ES
ST = Development
L = Local
O = DecentraLabs
OU = Development
CN = localhost

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
EOF

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$TEMP_SSL_DIR/privkey.pem" \
        -out "$TEMP_SSL_DIR/fullchain.pem" \
        -config "$TEMP_SSL_DIR/openssl.conf" \
        -extensions v3_req

    # NOTE: JWT keys (private_key.pem, public_key.pem) are generated by
    # blockchain-services entrypoint, not here. OpenResty only needs SSL certs.

    if [ -f "$TEMP_SSL_DIR/fullchain.pem" ] && [ -f "$TEMP_SSL_DIR/privkey.pem" ]; then
        cp "$TEMP_SSL_DIR/fullchain.pem" "$CERT_FILE"
        cp "$TEMP_SSL_DIR/privkey.pem" "$KEY_FILE"
        set_ssl_permissions
        date +%s > "$SELF_SIGNED_MARKER" 2>/dev/null || true
        echo "Self-signed SSL certificates generated successfully"
        echo "   Valid for: localhost, *.localhost, 127.0.0.1"
        echo "   WARNING: These are self-signed certificates for development only!"
    else
        echo "Failed to generate certificates - this will cause nginx startup failure"
        exit 1
    fi
}

is_localhost_self_signed() {
    subj=$(openssl x509 -in "$CERT_FILE" -noout -subject 2>/dev/null || echo "")
    issuer=$(openssl x509 -in "$CERT_FILE" -noout -issuer 2>/dev/null || echo "")
    echo "$subj" | grep -q "CN=localhost" && echo "$issuer" | grep -q "CN=localhost"
}

is_acme_cert() {
    # Check if certificate is issued by Let's Encrypt or other ACME CA
    issuer=$(openssl x509 -in "$CERT_FILE" -noout -issuer 2>/dev/null || echo "")
    echo "$issuer" | grep -qiE "(Let's Encrypt|R3|R4|E1|E2|ISRG|ZeroSSL)"
}

get_cert_days_until_expiry() {
    end_date=$(openssl x509 -in "$CERT_FILE" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
    if [ -z "$end_date" ]; then
        echo "unknown"
        return
    fi
    end_epoch=$(
        date -d "$end_date" +%s 2>/dev/null ||
        date -j -f "%b %d %H:%M:%S %Y %Z" "$end_date" +%s 2>/dev/null ||
        date -u -D "%b %e %H:%M:%S %Y %Z" -d "$end_date" +%s 2>/dev/null ||
        echo ""
    )
    if [ -z "$end_epoch" ]; then
        echo "unknown"
        return
    fi
    now_epoch=$(date +%s)
    days=$(( (end_epoch - now_epoch) / 86400 ))
    echo "$days"
}

cert_expires_within() {
    threshold_seconds="$1"
    openssl x509 -checkend "$threshold_seconds" -noout -in "$CERT_FILE" >/dev/null 2>&1
}

renew_acme_cert() {
    if [ -z "${CERTBOT_DOMAINS:-}" ] || [ -z "${CERTBOT_EMAIL:-}" ]; then
        echo "ACME renewal skipped: CERTBOT_DOMAINS or CERTBOT_EMAIL not set"
        return 1
    fi
    
    echo "Attempting ACME certificate renewal..."
    mkdir -p "$CERTBOT_WEBROOT"
    
    # Try renewal first (faster if cert exists)
    if certbot renew --webroot -w "$CERTBOT_WEBROOT" --quiet --deploy-hook "echo 'Certificate renewed successfully'" 2>/dev/null; then
        echo "ACME certificate renewed via certbot renew"
        return 0
    fi
    
    # If renewal fails, try obtaining a new cert
    domain_args=""
    for domain in $(echo "$CERTBOT_DOMAINS" | tr ',' ' '); do
        domain_args="$domain_args -d $domain"
    done
    
    if certbot certonly --webroot -w "$CERTBOT_WEBROOT" \
        $domain_args \
        --email "$CERTBOT_EMAIL" \
        --agree-tos --non-interactive --quiet 2>/dev/null; then
        
        # Copy new certs to expected location
        primary_domain=$(echo "$CERTBOT_DOMAINS" | cut -d',' -f1)
        cp "/etc/letsencrypt/live/$primary_domain/fullchain.pem" "$CERT_FILE"
        cp "/etc/letsencrypt/live/$primary_domain/privkey.pem" "$KEY_FILE"
        chmod 644 "$CERT_FILE"
        chmod 600 "$KEY_FILE"
        echo "ACME certificate obtained and installed"
        return 0
    fi
    
    echo "ACME certificate renewal failed"
    return 1
}

# Check if certificates exist or need renewal
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    # Try ACME first if configured
    if [ -n "${CERTBOT_DOMAINS:-}" ] && [ -n "${CERTBOT_EMAIL:-}" ]; then
        if ! renew_acme_cert; then
            echo "ACME failed, falling back to self-signed"
            generate_self_signed
        fi
    else
        generate_self_signed
    fi
else
    echo "SSL certificates found"
    set_ssl_permissions
    days_left=$(get_cert_days_until_expiry)
    echo "   Days until expiry: $days_left"
    
    if is_acme_cert; then
        # ACME cert: renew at 30 days before expiry
        if ! cert_expires_within "$RENEW_THRESHOLD_SECONDS"; then
            echo "   Status: ACME certificate expires in less than 30 days. Renewing..."
            if renew_acme_cert; then
                echo "   ACME certificate renewed successfully"
            else
                echo "   Warning: ACME renewal failed - will retry later"
            fi
        else
            echo "   Status: Valid ACME certificate"
        fi
    elif is_localhost_self_signed; then
        # Self-signed cert: regenerate at 10 days before expiry
        if ! cert_expires_within "$SELF_SIGNED_RENEW_THRESHOLD"; then
            echo "   Status: Self-signed certificate expiring soon. Regenerating..."
            generate_self_signed
        else
            echo "   Status: Valid self-signed certificate"
        fi
    else
        # User-provided cert: warn but don't replace
        if [ "$days_left" -lt 30 ]; then
            echo "   Warning: User-provided certificate expires in $days_left days!"
            echo "   Please renew manually or configure CERTBOT_DOMAINS and CERTBOT_EMAIL"
        else
            echo "   Status: Valid user-provided certificate"
        fi
    fi
fi

# Bootstrap JWT public key (local generation in Full mode or remote sync in Lite mode).
# Full mode reads the backend-generated key from the dedicated read-only mount;
# Lite mode owns the certs/ copy downloaded from the external issuer.
REMOTE_JWT_PUBLIC_KEY="$SSL_DIR/public_key.pem"
JWT_PREVIOUS_PUBLIC_KEY="$SSL_DIR/previous_public_key.pem"
JWT_PREVIOUS_ISSUED_MARKER="$SSL_DIR/.previous_public_key_issued"
JWT_ACTIVE_SNAPSHOT="$SSL_DIR/.active_public_key.pem"
JWT_KEY_OVERLAP_SECONDS="${JWT_KEY_OVERLAP_SECONDS:-14400}"
JWT_KEY_REFRESH_INTERVAL_SECONDS="${JWT_KEY_REFRESH_INTERVAL_SECONDS:-300}"
JWT_KEY_CONTEXT="$SSL_DIR/.jwt-key-context"
FULL_JWT_PUBLIC_KEY="/etc/openresty/jwt-keys/public_key.pem"
JWT_PUBLIC_KEY="$REMOTE_JWT_PUBLIC_KEY"
LOCAL_ISSUER="$(build_local_issuer)"
ISSUER_OVERRIDE="$(trim "${ISSUER:-}" | sed 's:/*$::')"
EFFECTIVE_ISSUER="$LOCAL_ISSUER"
jwt_key_sync_mode="local"
if [ -n "$ISSUER_OVERRIDE" ]; then
    EFFECTIVE_ISSUER="$ISSUER_OVERRIDE"
fi
if [ -n "$ISSUER_OVERRIDE" ] && [ "$EFFECTIVE_ISSUER" != "$LOCAL_ISSUER" ]; then
    jwt_key_sync_mode="remote"
    JWT_PUBLIC_KEY="$REMOTE_JWT_PUBLIC_KEY"
fi

echo "=== JWT Public Key Bootstrap ==="
echo "Remote issuer key file: $REMOTE_JWT_PUBLIC_KEY"
echo "Full-mode backend key file: $FULL_JWT_PUBLIC_KEY"
echo "Local issuer: $LOCAL_ISSUER"
echo "Effective issuer: $EFFECTIVE_ISSUER"

# A mode/issuer change is a trust-boundary change.  Never carry an overlap
# key from the previous issuer into the new one, and force Lite to download
# the new active key instead of treating a stale file as current.
context_value="${jwt_key_sync_mode}|${EFFECTIVE_ISSUER}"
context_hash="$(printf '%s' "$context_value" | (sha256sum 2>/dev/null || shasum -a 256) | awk '{print $1}')"
stored_context="$(cat "$JWT_KEY_CONTEXT" 2>/dev/null || true)"
if [ "$stored_context" != "$context_hash" ]; then
    echo "JWT issuer/mode changed; clearing rotation overlap state"
    rm -f "$JWT_PREVIOUS_PUBLIC_KEY" "$JWT_PREVIOUS_ISSUED_MARKER" "$JWT_ACTIVE_SNAPSHOT"
    if [ "$jwt_key_sync_mode" = "remote" ]; then
        rm -f "$REMOTE_JWT_PUBLIC_KEY"
    fi
    printf '%s\n' "$context_hash" > "${JWT_KEY_CONTEXT}.tmp"
    mv -f "${JWT_KEY_CONTEXT}.tmp" "$JWT_KEY_CONTEXT"
fi

if [ -n "$ISSUER_OVERRIDE" ] && [ "$EFFECTIVE_ISSUER" != "$LOCAL_ISSUER" ]; then
    echo "Detected external issuer mode (Lite): syncing JWT public key from issuer origin"

    wait_count=0
    max_wait=60
    synced=false
    while [ "$synced" != "true" ] && [ $wait_count -lt $max_wait ]; do
        sync_jwt_public_key_from_issuer "$EFFECTIVE_ISSUER"
        sync_result=$?
        if [ $sync_result -eq 0 ] || [ $sync_result -eq 10 ]; then
            synced=true
            break
        fi
        echo "Retrying JWT key sync in 2s... (${wait_count}s)"
        sleep 2
        wait_count=$((wait_count + 2))
    done

    if [ -f "$JWT_PUBLIC_KEY" ]; then
        echo "JWT public key ready for external issuer mode"
    else
        echo "WARNING: JWT public key sync failed after ${max_wait}s - JWT validation will fail until next refresh"
    fi
else
    JWT_PUBLIC_KEY="$FULL_JWT_PUBLIC_KEY"
    echo "Detected local issuer mode (Full): waiting for blockchain-services to generate JWT keys"
    wait_count=0
    max_wait=60
    while [ ! -f "$JWT_PUBLIC_KEY" ] && [ $wait_count -lt $max_wait ]; do
        echo "Waiting for blockchain-services to generate JWT keys... (${wait_count}s)"
        sleep 2
        wait_count=$((wait_count + 2))
    done

    if [ -f "$JWT_PUBLIC_KEY" ]; then
        echo "JWT public key found"
    else
        echo "WARNING: JWT public key not found after ${max_wait}s - JWT validation will fail until key is available"
        echo "blockchain-services should generate it on startup"
    fi
fi

if [ "$jwt_key_sync_mode" = "local" ] && is_valid_public_key "$FULL_JWT_PUBLIC_KEY"; then
    if [ ! -f "$JWT_ACTIVE_SNAPSHOT" ]; then
        atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"
    fi
fi

echo "=== Starting OpenResty ==="

# Export environment variables that nginx needs to access
export LAB_MANAGER_TOKEN="${LAB_MANAGER_TOKEN:-}"

# Background watcher: reload OpenResty if cert/key change on disk
watch_certs() {
    last_cert_ts=$(stat -c %Y "$CERT_FILE" 2>/dev/null || stat -f %m "$CERT_FILE" 2>/dev/null || echo 0)
    last_key_ts=$(stat -c %Y "$KEY_FILE" 2>/dev/null || stat -f %m "$KEY_FILE" 2>/dev/null || echo 0)
    while true; do
        sleep 43200  # 12h
        cert_ts=$(stat -c %Y "$CERT_FILE" 2>/dev/null || stat -f %m "$CERT_FILE" 2>/dev/null || echo 0)
        key_ts=$(stat -c %Y "$KEY_FILE" 2>/dev/null || stat -f %m "$KEY_FILE" 2>/dev/null || echo 0)
        if [ "$cert_ts" != "$last_cert_ts" ] || [ "$key_ts" != "$last_key_ts" ]; then
            echo "Certificate/key changed on disk. Reloading OpenResty..."
            /usr/local/openresty/bin/openresty -s reload || true
            last_cert_ts="$cert_ts"
            last_key_ts="$key_ts"
        fi
    done
}

watch_certs &

retire_previous_jwt_key() {
    issued_ts="$(cat "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || echo 0)"
    now_ts="$(date +%s)"
    case "$issued_ts" in
        ''|*[!0-9]*) return 1 ;;
    esac
    if [ "$issued_ts" -gt 0 ] && [ $((now_ts - issued_ts)) -ge "$JWT_KEY_OVERLAP_SECONDS" ]; then
        rm -f "$JWT_PREVIOUS_PUBLIC_KEY" "$JWT_PREVIOUS_ISSUED_MARKER"
        echo "Expired previous JWT public key overlap"
        return 0
    fi
    return 1
}

# blockchain-services rotates the Full-mode key in-place.  Keep the last
# complete key in the writable cert volume and reload only after the new PEM
# validates, giving OpenResty a bounded current/previous overlap window.
watch_full_jwt_public_key() {
    if [ "$jwt_key_sync_mode" != "local" ]; then
        return
    fi
    while true; do
        sleep 60
        if retire_previous_jwt_key; then
            /usr/local/openresty/bin/openresty -s reload || true
        fi
        if ! is_valid_public_key "$FULL_JWT_PUBLIC_KEY"; then
            echo "WARNING: Full-mode JWT public key is missing or invalid; retaining current key"
            continue
        fi
        if [ ! -f "$JWT_ACTIVE_SNAPSHOT" ]; then
            atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"
            echo "Full-mode JWT public key became available; reloading OpenResty"
            /usr/local/openresty/bin/openresty -s reload || true
            continue
        fi
        if ! cmp -s "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"; then
            if ! atomic_copy "$JWT_ACTIVE_SNAPSHOT" "$JWT_PREVIOUS_PUBLIC_KEY"; then
                echo "WARNING: Could not preserve previous JWT key; deferring rotation"
                continue
            fi
            date +%s > "$JWT_PREVIOUS_ISSUED_MARKER" 2>/dev/null || true
            if ! atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"; then
                echo "WARNING: Could not snapshot new JWT key; deferring rotation"
                continue
            fi
            echo "Full-mode JWT public key changed; reloading OpenResty with overlap key"
            /usr/local/openresty/bin/openresty -s reload || true
        fi
    done
}

watch_full_jwt_public_key &

auto_rotate_self_signed() {
    # Only rotate self-signed certs when ACME is not configured
    if [ -n "${CERTBOT_DOMAINS:-}" ] && [ -n "${CERTBOT_EMAIL:-}" ]; then
        return
    fi
    while true; do
        sleep 86400  # daily check
        if ! is_localhost_self_signed; then
            continue
        fi
        issued_ts=$(cat "$SELF_SIGNED_MARKER" 2>/dev/null || echo 0)
        now_ts=$(date +%s)
        age=$((now_ts - issued_ts))
        if [ "$age" -ge "$SELF_SIGNED_MAX_AGE_SECONDS" ]; then
            echo "Self-signed certificate older than 85 days - rotating..."
            generate_self_signed
            /usr/local/openresty/bin/openresty -s reload || true
        fi
    done
}

auto_rotate_self_signed &

# Background ACME renewal watcher (runs twice daily for Let's Encrypt best practices)
auto_renew_acme() {
    if [ -z "${CERTBOT_DOMAINS:-}" ] || [ -z "${CERTBOT_EMAIL:-}" ]; then
        return
    fi
    while true; do
        sleep 43200  # 12 hours
        if ! is_acme_cert; then
            continue
        fi
        days_left=$(get_cert_days_until_expiry)
        if ! cert_expires_within "$RENEW_THRESHOLD_SECONDS"; then
            echo "ACME certificate expires in $days_left days - attempting renewal..."
            if renew_acme_cert; then
                echo "ACME certificate renewed. Reloading OpenResty..."
                /usr/local/openresty/bin/openresty -s reload || true
            fi
        fi
    done
}

auto_renew_acme &

auto_refresh_jwt_public_key() {
    if [ "$jwt_key_sync_mode" != "remote" ]; then
        return
    fi
    while true; do
        sleep "$JWT_KEY_REFRESH_INTERVAL_SECONDS"
        if retire_previous_jwt_key; then
            /usr/local/openresty/bin/openresty -s reload || true
        fi
        sync_jwt_public_key_from_issuer "$EFFECTIVE_ISSUER"
        sync_result=$?
        if [ $sync_result -eq 10 ]; then
            echo "JWT public key changed - reloading OpenResty"
            /usr/local/openresty/bin/openresty -s reload || true
        elif [ $sync_result -ne 0 ]; then
            echo "WARNING: JWT public key refresh failed; will retry every hour until it succeeds"
            # Retry loop: attempt once per hour until the remote is reachable again
            retry_interval=3600
            while true; do
                sleep $retry_interval
                sync_jwt_public_key_from_issuer "$EFFECTIVE_ISSUER"
                retry_result=$?
                if [ $retry_result -eq 0 ] || [ $retry_result -eq 10 ]; then
                    if [ $retry_result -eq 10 ]; then
                        echo "JWT public key updated on retry - reloading OpenResty"
                        /usr/local/openresty/bin/openresty -s reload || true
                    else
                        echo "JWT public key confirmed up-to-date after retry"
                    fi
                    break  # success – return to 24h cycle
                fi
                echo "WARNING: JWT public key refresh retry failed; will try again in ${retry_interval}s"
            done
        fi
    done
}

auto_refresh_jwt_public_key &

exec /usr/local/openresty/bin/openresty -g "daemon off;"
