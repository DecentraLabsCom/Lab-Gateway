#!/bin/sh
# =================================================================
# OpenResty SSL Certificate Initialization Script
# =================================================================

SSL_DIR="/etc/ssl/private"
CERT_FILE="$SSL_DIR/fullchain.pem"
KEY_FILE="$SSL_DIR/privkey.pem"
PUBLIC_KEY_FILE="$SSL_DIR/public_key.pem"
TEMP_SSL_DIR="/tmp/ssl"

echo "=== OpenResty SSL Certificate Check ==="
echo "Certificate: $CERT_FILE"
echo "Private Key: $KEY_FILE"

# Create SSL directory if it doesn't exist
mkdir -p "$SSL_DIR"

# Check if certificates exist
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "SSL certificates not found - generating self-signed certificates for development"
    
    # Create temporary SSL directory and generate certificates there
    mkdir -p "$TEMP_SSL_DIR"
    
    # Create OpenSSL config file for proper certificate generation
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

    # Generate self-signed certificate for localhost
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$TEMP_SSL_DIR/privkey.pem" \
        -out "$TEMP_SSL_DIR/fullchain.pem" \
        -config "$TEMP_SSL_DIR/openssl.conf" \
        -extensions v3_req
    
    # Generate JWT public key for auth-service (if not exists)
    if [ ! -f "$PUBLIC_KEY_FILE" ]; then
        echo "Generating JWT public key for auth-service..."
        openssl genrsa -out /tmp/jwt_private.pem 2048
        openssl rsa -in /tmp/jwt_private.pem -pubout -out "$PUBLIC_KEY_FILE"
        rm -f /tmp/jwt_private.pem
    fi
    
    # Copy generated certificates to the SSL directory
    if [ -f "$TEMP_SSL_DIR/fullchain.pem" ] && [ -f "$TEMP_SSL_DIR/privkey.pem" ]; then
        cp "$TEMP_SSL_DIR/fullchain.pem" "$CERT_FILE"
        cp "$TEMP_SSL_DIR/privkey.pem" "$KEY_FILE"
        chmod 644 "$CERT_FILE"
        chmod 600 "$KEY_FILE"
        chmod 644 "$PUBLIC_KEY_FILE"
        echo "✅ Self-signed certificates generated successfully"
        echo "   Valid for: localhost, *.localhost, 127.0.0.1"
        echo "   JWT Public Key: $PUBLIC_KEY_FILE"
        echo "   WARNING: These are self-signed certificates for development only!"
    else
        echo "❌ Failed to generate certificates - this will cause nginx startup failure"
        exit 1
    fi
else
    echo "✅ SSL certificates found"
    # Validate certificate
    if openssl x509 -in "$CERT_FILE" -noout -checkend 86400 2>/dev/null; then
        echo "   Status: Valid (expires in more than 24 hours)"
    else
        echo "   Status: Warning - Certificate expires soon or is invalid"
    fi
fi

echo "=== Starting OpenResty ==="
exec /usr/local/openresty/bin/openresty -g "daemon off;"