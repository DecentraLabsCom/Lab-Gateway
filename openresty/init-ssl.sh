#!/bin/sh
# =================================================================
# OpenResty SSL Certificate Initialization Script
# =================================================================

SSL_DIR="/etc/ssl/private"
CERT_FILE="$SSL_DIR/fullchain.pem"
KEY_FILE="$SSL_DIR/privkey.pem"
PUBLIC_KEY_FILE="$SSL_DIR/public_key.pem"
TEMP_SSL_DIR="/tmp/ssl"
RENEW_THRESHOLD_SECONDS=$((10 * 24 * 3600))  # 10 days (self-signed regeneration threshold)
SELF_SIGNED_MARKER="$SSL_DIR/.selfsigned_issued"
SELF_SIGNED_MAX_AGE_SECONDS=$((87 * 24 * 3600))

echo "=== OpenResty SSL Certificate Check ==="
echo "Certificate: $CERT_FILE"
echo "Private Key: $KEY_FILE"

# Create SSL directory if it doesn't exist
mkdir -p "$SSL_DIR"

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

    if [ ! -f "$PUBLIC_KEY_FILE" ]; then
        echo "Generating JWT public key for blockchain-services..."
        openssl genrsa -out /tmp/jwt_private.pem 2048
        openssl rsa -in /tmp/jwt_private.pem -pubout -out "$PUBLIC_KEY_FILE"
        rm -f /tmp/jwt_private.pem
    fi

    if [ -f "$TEMP_SSL_DIR/fullchain.pem" ] && [ -f "$TEMP_SSL_DIR/privkey.pem" ]; then
        cp "$TEMP_SSL_DIR/fullchain.pem" "$CERT_FILE"
        cp "$TEMP_SSL_DIR/privkey.pem" "$KEY_FILE"
        chmod 644 "$CERT_FILE"
        chmod 600 "$KEY_FILE"
        chmod 644 "$PUBLIC_KEY_FILE"
        date +%s > "$SELF_SIGNED_MARKER" 2>/dev/null || true
        echo "✔ Self-signed certificates generated successfully"
        echo "   Valid for: localhost, *.localhost, 127.0.0.1"
        echo "   JWT Public Key: $PUBLIC_KEY_FILE"
        echo "   WARNING: These are self-signed certificates for development only!"
    else
        echo "✖ Failed to generate certificates - this will cause nginx startup failure"
        exit 1
    fi
}

is_localhost_self_signed() {
    subj=$(openssl x509 -in "$CERT_FILE" -noout -subject 2>/dev/null || echo "")
    issuer=$(openssl x509 -in "$CERT_FILE" -noout -issuer 2>/dev/null || echo "")
    echo "$subj" | grep -q "CN=localhost" && echo "$issuer" | grep -q "CN=localhost"
}

# Check if certificates exist or need renewal
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    generate_self_signed
else
    echo "✔ SSL certificates found"
    if openssl x509 -in "$CERT_FILE" -noout -checkend "$RENEW_THRESHOLD_SECONDS" 2>/dev/null; then
        echo "   Status: Valid (expires in more than 10 days)"
    else
        if is_localhost_self_signed; then
            echo "   Status: Expiring soon/invalid and appears self-signed localhost. Regenerating..."
            generate_self_signed
        else
            echo "   Status: Warning - Certificate expires soon or is invalid (user-provided cert will not be replaced)"
        fi
    fi
fi

echo "=== Starting OpenResty ==="

# Export environment variables that nginx needs to access
export OPS_SECRET="${OPS_SECRET:-}"

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

exec /usr/local/openresty/bin/openresty -g "daemon off;"
