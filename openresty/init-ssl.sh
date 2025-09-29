#!/bin/sh

# =================================================================
# SSL Certificate Initialization Script for OpenResty
# Automatically generates self-signed certificates if they don't exist
# =================================================================

CERT_DIR="/etc/ssl/private"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"
PUBLIC_KEY_FILE="$CERT_DIR/public_key.pem"

echo "Initializing SSL certificates..."

# Create certificate directory if it doesn't exist  
mkdir -p "$CERT_DIR"

# Check if certificates already exist
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "SSL certificates already exist, skipping generation"
    
    # Validate certificates
    if ! openssl x509 -in "$CERT_FILE" -text -noout >/dev/null 2>&1; then
        echo "Warning: SSL certificate appears to be invalid"
    else
        echo "SSL certificates validated successfully"
    fi
else  
    echo "SSL certificates not found, generating self-signed certificates for development..."
    
    # Create OpenSSL configuration for proper certificate generation
    cat > /tmp/openssl.conf <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = ES
ST = Madrid
L = Madrid
O = DecentraLabs
OU = Development
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    # Generate private key
    openssl genrsa -out "$KEY_FILE" 2048
    if [ $? -ne 0 ]; then
        echo "Error: Failed to generate private key"
        exit 1
    fi
    
    # Generate certificate signing request
    openssl req -new -key "$KEY_FILE" -out /tmp/server.csr -config /tmp/openssl.conf
    if [ $? -ne 0 ]; then
        echo "Error: Failed to generate certificate signing request"
        exit 1
    fi
    
    # Generate self-signed certificate
    openssl x509 -req -in /tmp/server.csr -signkey "$KEY_FILE" -out "$CERT_FILE" \
        -days 365 -extensions v3_req -extfile /tmp/openssl.conf
    if [ $? -ne 0 ]; then
        echo "Error: Failed to generate certificate"
        exit 1
    fi
    
    # Generate JWT public key for auth-service (if not exists)
    if [ ! -f "$PUBLIC_KEY_FILE" ]; then
        echo "Generating JWT public key for auth-service..."
        openssl genrsa -out /tmp/jwt_private.pem 2048
        openssl rsa -in /tmp/jwt_private.pem -pubout -out "$PUBLIC_KEY_FILE"
        rm -f /tmp/jwt_private.pem
    fi
    
    # Set proper permissions
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    chmod 644 "$PUBLIC_KEY_FILE"
    
    # Clean up temporary files
    rm -f /tmp/server.csr /tmp/openssl.conf
    
    echo "Self-signed SSL certificates generated successfully"
    echo "Certificate: $CERT_FILE"
    echo "Private Key: $KEY_FILE"
    echo "JWT Public Key: $PUBLIC_KEY_FILE"
    echo "Note: These are self-signed certificates for development only"
fi

echo "SSL initialization completed"