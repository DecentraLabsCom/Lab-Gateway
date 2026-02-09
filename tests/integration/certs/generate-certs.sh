#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/privkey.pem"
CERT_FILE="$SCRIPT_DIR/fullchain.pem"
TMP_CONF="$(mktemp)"

cleanup() {
  rm -f "$TMP_CONF"
}
trap cleanup EXIT

cat >"$TMP_CONF" <<'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

echo "Generating self-signed integration certificates in: $SCRIPT_DIR"
openssl req \
  -x509 \
  -nodes \
  -newkey rsa:2048 \
  -days 365 \
  -keyout "$KEY_FILE" \
  -out "$CERT_FILE" \
  -config "$TMP_CONF"

chmod 600 "$KEY_FILE" || true
chmod 644 "$CERT_FILE" || true

echo "Done:"
echo "  - $KEY_FILE"
echo "  - $CERT_FILE"
