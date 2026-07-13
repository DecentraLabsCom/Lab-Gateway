#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 <lite-public-origin> <full-public-origin> [output-file]" >&2
    exit 2
fi

lite_public_origin="${1%/}"
full_origin="${2%/}"
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${root_dir}/.env"

if [ ! -f "$env_file" ]; then
    echo "${env_file} does not exist; configure the Full gateway first" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to update the trusted gateway map safely" >&2
    exit 1
fi

IFS=$'\t' read -r lite_public_origin full_origin gateway_id < <(python3 - "$lite_public_origin" "$full_origin" <<'PY'
import sys
from urllib.parse import urlsplit

def validate(label, raw):
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise SystemExit(f"{label} must be an absolute https origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise SystemExit(f"{label} must not contain credentials, path, query or fragment")
    host = parsed.hostname.lower().rstrip(".")
    if not host or len(host) > 253 or any(not part or len(part) > 63 for part in host.split(".")):
        raise SystemExit(f"{label} has an invalid hostname")
    port = parsed.port
    origin = f"https://{host}" + (f":{port}" if port and port != 443 else "")
    return origin, host

lite_origin, gateway_id = validate("lite-public-origin", sys.argv[1])
full_origin, _ = validate("full-public-origin", sys.argv[2])
print(lite_origin, full_origin, gateway_id, sep="\t")
PY
)
if [ -z "$lite_public_origin" ] || [ -z "$full_origin" ] || [ -z "$gateway_id" ]; then
    echo "Unable to validate Lite and Full public origins" >&2
    exit 2
fi
output_file="${3:-lite-trust-${gateway_id}.env}"

redeemer="acr_$(openssl rand -hex 32)"
secret="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n')"

python3 - "$env_file" "$gateway_id" "$secret" "$redeemer" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
gateway_id, secret, redeemer = sys.argv[2], sys.argv[3], sys.argv[4]
lines = path.read_text(encoding="utf-8").splitlines()
for key, value in (
    ("SESSION_OBSERVER_CREDENTIALS_JSON", secret),
    ("ACCESS_CODE_REDEEMER_CREDENTIALS_JSON", redeemer),
):
    current = next((line.split("=", 1)[1] for line in lines if line.startswith(key + "=")), "{}")
    credentials = json.loads(current or "{}")
    credentials[gateway_id.lower()] = value
    replacement = key + "=" + json.dumps(credentials, separators=(",", ":"), sort_keys=True)
    found = any(line.startswith(key + "=") for line in lines)
    lines = [replacement if line.startswith(key + "=") else line for line in lines]
    if not found:
        lines.append(replacement)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

umask 077
{
    echo "ISSUER=${full_origin}/auth"
    echo "SERVER_NAME=${gateway_id}"
    echo "AUTH_ACCESS_CODE_REDEEMER_TOKEN=${redeemer}"
    echo "ACCESS_AUDIT_URL=${full_origin}/access-audit/internal/session-observed"
    echo "SESSION_OBSERVER_GATEWAY_ID=${gateway_id}"
    echo "SESSION_OBSERVER_SIGNING_SECRET=${secret}"
    echo "FMU_GATEWAY_ID=${gateway_id}"
    echo "FMU_JWT_AUDIENCE=${lite_public_origin}/fmu"
    echo "AUTH_SESSION_TICKET_ISSUE_URL=${full_origin}/auth/fmu/session-ticket/issue"
    echo "AUTH_SESSION_TICKET_REDEEM_URL=${full_origin}/auth/fmu/session-ticket/redeem"
} > "$output_file"
chmod 600 "$output_file"
echo "Created ${output_file}; transfer it securely and delete it after Lite setup."
echo "Restart blockchain-services on Full so the new gateway credential is loaded."
