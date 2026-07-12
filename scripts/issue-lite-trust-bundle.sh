#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 <gateway-id> <full-public-origin> [output-file]" >&2
    exit 2
fi

gateway_id="$1"
full_origin="${2%/}"
output_file="${3:-lite-trust-${gateway_id}.env}"
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${root_dir}/.env"

if ! [[ "$gateway_id" =~ ^[A-Za-z0-9._-]{3,128}$ ]]; then
    echo "gateway-id must contain only letters, digits, dot, underscore or hyphen" >&2
    exit 2
fi
if ! [[ "$full_origin" =~ ^https:// ]]; then
    echo "full-public-origin must use https" >&2
    exit 2
fi
if [ ! -f "$env_file" ]; then
    echo "${env_file} does not exist; configure the Full gateway first" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to update the trusted gateway map safely" >&2
    exit 1
fi

redeemer="$(grep -E '^AUTH_ACCESS_CODE_REDEEMER_TOKEN=' "$env_file" | head -n1 | cut -d= -f2-)"
if [ -z "$redeemer" ] || [ "$redeemer" = "CHANGE_ME" ]; then
    echo "Full gateway access-code redeemer credential is not configured" >&2
    exit 1
fi
secret="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n')"

python3 - "$env_file" "$gateway_id" "$secret" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
gateway_id, secret = sys.argv[2], sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
key = "SESSION_OBSERVER_CREDENTIALS_JSON"
current = next((line.split("=", 1)[1] for line in lines if line.startswith(key + "=")), "{}")
credentials = json.loads(current or "{}")
credentials[gateway_id] = secret
replacement = key + "=" + json.dumps(credentials, separators=(",", ":"), sort_keys=True)
lines = [replacement if line.startswith(key + "=") else line for line in lines]
if not any(line.startswith(key + "=") for line in path.read_text(encoding="utf-8").splitlines()):
    lines.append(replacement)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

umask 077
{
    echo "ISSUER=${full_origin}/auth"
    echo "AUTH_ACCESS_CODE_REDEEMER_TOKEN=${redeemer}"
    echo "ACCESS_AUDIT_URL=${full_origin}/access-audit/internal/session-observed"
    echo "SESSION_OBSERVER_GATEWAY_ID=${gateway_id}"
    echo "SESSION_OBSERVER_SIGNING_SECRET=${secret}"
} > "$output_file"
chmod 600 "$output_file"
echo "Created ${output_file}; transfer it securely and delete it after Lite setup."
echo "Restart blockchain-services on Full so the new gateway credential is loaded."
