# Installation Guide — Manual Docker Compose

Use this guide if you want full control over every configuration step without running
the interactive setup script.

Before editing environment files, choose the control-plane topology in
[Deployment architectures](../deployment-architectures.md). The complete
variable ownership and optional-profile reference is
[Configuration reference](../reference/configuration.md).

## Prerequisites

| Requirement | Minimum version |
|---|---|
| Docker Engine (Linux) or Docker Desktop (Windows/macOS) | 20.10+ |
| Docker Compose plugin | 2.14.0+ (`docker compose`; legacy `docker-compose` is not supported) |
| Git | any recent version |
| 2 CPU cores, 4 GB RAM, 20 GB free disk | — |

## Step 1 — Clone the repository

```bash
git clone --recurse-submodules https://github.com/DecentraLabsCom/Lab-Gateway.git /srv/lab-gateway
cd /srv/lab-gateway
```

If you already cloned without `--recurse-submodules`, initialise the submodule manually:

```bash
git submodule update --init --recursive
```

## Step 2 — Create environment files

```bash
cp .env.example .env
cp blockchain-services/.env.example blockchain-services/.env
```

## Step 3 — Configure `.env` (Gateway)

Open `.env` and set at minimum:

```env
# Your public domain
SERVER_NAME=lab.your-institution.edu

# Strong passwords — do not leave defaults
MYSQL_ROOT_PASSWORD=change_to_strong_password
GUACAMOLE_MYSQL_PASSWORD=change_to_strong_password
BLOCKCHAIN_MYSQL_PASSWORD=change_to_strong_password
OPS_BACKEND_MYSQL_PASSWORD=change_to_strong_password
OPS_GUACAMOLE_MYSQL_PASSWORD=change_to_strong_password
GUACAMOLE_MYSQL_USER=guacamole_app
BLOCKCHAIN_MYSQL_USER=blockchain_app
OPS_BACKEND_MYSQL_USER=ops_backend
OPS_GUACAMOLE_MYSQL_USER=ops_guac
OPS_SECRETS_KEY=<stable-fernet-key>
WINRM_MANAGEMENT_CIDRS=10.7.74.0/24

# Guacamole admin (do not use 'guacadmin' in production)
GUAC_ADMIN_USER=admin
GUAC_ADMIN_PASS=change_to_strong_password

# Protect wallet/billing routes from public networks
ADMIN_ACCESS_TOKEN=change_to_random_token

# Protect lab manager and ops endpoints
LAB_MANAGER_TOKEN=change_to_random_token

# Comma-separated origins allowed for CORS (your Marketplace URL)
CORS_ALLOWED_ORIGINS=https://marketplace-decentralabs.vercel.app

# Required by Compose interpolation; use the public FMU origin when FMU is enabled
FMU_JWT_AUDIENCE=https://lab.your-institution.edu/fmu
```

For a Full gateway, configure the credentials used by opaque access-code
redemption and FMU session observation. The JSON values must be valid JSON
objects, and the key must match the normalized `SERVER_NAME` exactly. Do not
use a `host:token` string:

```env
AUTH_ACCESS_CODE_REDEEMER_TOKEN=<random-redeemer-token>
ACCESS_CODE_ENCRYPTION_KEY=<url-safe-base64-key-for-32-bytes>
ACCESS_CODE_REDEEMER_CREDENTIALS_JSON={"lab.your-institution.edu":"<random-redeemer-token>"}
SESSION_OBSERVER_GATEWAY_ID=lab.your-institution.edu
SESSION_OBSERVER_SIGNING_SECRET=<url-safe-base64-secret-for-32-bytes>
SESSION_OBSERVER_CREDENTIALS_JSON={"lab.your-institution.edu":"<url-safe-base64-secret-for-32-bytes>"}
```

Generate the encryption key and observer secret independently. Both must decode
to exactly 32 bytes:

```bash
openssl rand -base64 32 | tr '+/' '-_' | tr -d '='
```

Run the command twice and use separate values. The redeemer token can be any
unique high-entropy secret; for example:

```bash
openssl rand -hex 32
```

Lite gateways must use the credentials and trust bundle issued by the remote
Full gateway instead of inventing local Full-mode maps.

## Step 3a — Generate Compose secret files

The Compose file uses host-backed secret files because several services run
with a read-only root filesystem. On Linux, do not run the commands below until
Step 5 is complete: `HOST_UID`, `HOST_GID` and the persistent directories must
be ready first. Then run the validator and generate the files before running
`docker compose config` or `docker compose up`.

Linux, macOS, or WSL:

```bash
python3 scripts/validate-gateway-env.py --env .env
bash scripts/sync-compose-secrets.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Validate-GatewayEnv.ps1 -EnvPath .\.env
powershell -ExecutionPolicy Bypass -File .\scripts\Sync-ComposeSecrets.ps1
```

Validate the rendered Compose model before starting services:

```bash
docker compose config --quiet
docker compose config --services
docker compose config --profiles
```

The command creates the ignored `secrets/` directory with mode `0750` and
`0644` files. The file mode must allow non-root services to read Compose's
mounted secrets; the directory still restricts local host access. Run it again
whenever a secret value in `.env` changes. Never commit or delete this
directory while the deployment is in use.

#### Gateway mode

**Full mode** (this institution issues its own JWTs):

```env
# Leave ISSUER empty — this is the default
ISSUER=
```

**Lite mode** (trust JWTs from an external full-mode gateway):

```env
ISSUER=https://auth-gateway.other-institution.edu/auth
BLOCKCHAIN_SERVICES_ENABLED=false
```

Lite is an access-plane mode, not a second issuer. The root Compose file keeps
the embedded `blockchain-services` container dormant
(`BLOCKCHAIN_SERVICES_ENABLED=false`) and OpenResty uses the remote issuer for
access-code, FMU and observation calls. For Full + N Lite or standalone `blockchain-services` + N
Lite, configure one trust bundle, gateway ID and explicit provisioner route per
Lite; see [Deployment Architectures](../deployment-architectures.md).

#### Bind address

```env
# Accessible from outside (production default)
OPENRESTY_BIND_ADDRESS=0.0.0.0

# Local only (development)
OPENRESTY_BIND_ADDRESS=127.0.0.1
```

#### Behind a NAT/router with port forwarding

If your institution exposes port 8043 externally but Docker listens on 443:

```env
HTTPS_PORT=8043
OPENRESTY_BIND_HTTPS_PORT=443
```

## Step 4 — Configure `blockchain-services/.env`

```env
# Smart contract address (from Smart-Contracts deployment)
CONTRACT_ADDRESS=0xYourContractAddress

# RPC endpoints (comma-separated for failover)
ETHEREUM_SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com,https://0xrpc.io/sep

# Provider features (required for full Lab Gateway mode)
BLOCKCHAIN_SERVICES_MODE=provider-consumer
FEATURES_PROVIDERS_ENABLED=true
FEATURES_PROVIDERS_REGISTRATION_ENABLED=true

# Origins allowed by the blockchain service
ALLOWED_ORIGINS=https://lab.your-institution.edu,https://marketplace-decentralabs.vercel.app
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem
```

Leave `INSTITUTIONAL_WALLET_ADDRESS` and `INSTITUTIONAL_WALLET_PASSWORD` empty — they
are populated automatically after you create or import a wallet through the web console.

## Step 5 — Set file ownership (Linux/macOS only)

Use the UID and GID of the non-root account that owns the deployment and runs
Docker commands. Do not leave the example values unless they are your actual
IDs:

```bash
id -u && id -g
```

Set the resulting values in `.env`:

```env
HOST_UID=1000
HOST_GID=1000
```

Create the bind-mounted directories before starting Compose. In particular,
`fmu-access-state` must be writable by the OpenResty UID because it stores
encrypted, durable FMU session mappings:

```bash
gateway_uid="$(id -u)"
gateway_gid="$(id -g)"

mkdir -p blockchain-data certs fmu-access-state lab-content fmu-data \
  fmu-proxy-runtime/binaries/linux64 \
  fmu-proxy-runtime/binaries/win64 \
  fmu-proxy-runtime/binaries/darwin64 \
  ops-data/guac-revocation-spool

sudo chown -R "${gateway_uid}:${gateway_gid}" \
  blockchain-data certs fmu-access-state lab-content
chmod 700 fmu-access-state
chmod 755 lab-content fmu-data fmu-proxy-runtime \
  fmu-proxy-runtime/binaries fmu-proxy-runtime/binaries/linux64 \
  fmu-proxy-runtime/binaries/win64 fmu-proxy-runtime/binaries/darwin64
chmod 700 ops-data ops-data/guac-revocation-spool
```

If you run the stack through `sudo`, preserve the deployment account's
`HOST_UID` and `HOST_GID`; do not silently replace them with root's IDs.

## Step 6 — Add SSL certificates

**Production** — place your CA-issued or Let's Encrypt certificates here:

```
certs/
├── fullchain.pem   # Full certificate chain
└── privkey.pem     # Private key
```

**Let's Encrypt (automated)** — set in `.env` and start with the `certbot` profile:

```env
CERTBOT_DOMAINS=lab.your-institution.edu
CERTBOT_EMAIL=admin@your-institution.edu
CERTBOT_STAGING=0
```

```bash
docker compose --profile certbot up -d
```

**Development** — self-signed certificates are generated automatically on first start
if `certs/` is empty.

## Step 7 — Start the stack

```bash
docker compose up -d --build
```

Watch the logs while containers initialise:

```bash
docker compose logs -f
```

Enable optional services only when they are configured and required. For
example, the production FMU facade is Station-only and uses its own profile:

```env
FMU_RUNNER_ENABLED=true
FMU_BACKEND_MODE=station
FMU_LOCAL_DEV_MODE=false
FMU_LOCAL_REALTIME_ENABLED=false
FMU_STATION_BASE_URL=https://station.internal.example
FMU_STATION_INTERNAL_TOKEN=<station-internal-token>
```

```bash
docker compose --profile fmu-runner up -d --build
```

For development-only local FMU execution, use `fmu-local-dev` instead; never
start both FMU profiles. Set the local mode explicitly in `.env`:

```env
FMU_RUNNER_ENABLED=true
FMU_BACKEND_MODE=local
FMU_LOCAL_DEV_MODE=true
FMU_LOCAL_REALTIME_ENABLED=true
```

```bash
docker compose --profile fmu-local-dev up -d --build openresty fmu-runner-local
```

The local runner needs `secrets/session_observer_signing_secret`, generated
from `SESSION_OBSERVER_SIGNING_SECRET`, to redeem FMU tickets and record
accepted sessions. It does not need Station or administrator credentials.

For local execution, place each published FMU in one of the supported layouts
and make its `accessKey`/`fmuFileName` match the configured resource:

```text
fmu-data/<accessKey>.fmu
fmu-data/<accessKey>/model.fmu
```

See [FMU data layout](../../fmu-data/README.md) for provider-scoped storage
and [FMI/FMU support](../fmi-fmu-support.md) for publication and validation.

`FMU_BACKEND_MODE` controls FMU execution location; Full/Lite authentication
controls the JWKS source independently. The setup scripts persist
`FMU_LOCAL_REALTIME_ENABLED=true` automatically when the local backend is
selected. Keep it `false` for the station-backed production profile. See the
[configuration reference](../reference/configuration.md).

## Step 8 — Verify health

```bash
# Gateway routing layer
curl -k https://localhost/health

# Blockchain services
curl -k https://localhost/auth/.well-known/openid-configuration
```

Both should return JSON without errors. The public health response is intentionally redacted; Lab Manager operators can use `/health/details` with the configured `LAB_MANAGER_TOKEN` for backend diagnostics.

When FMU is enabled, verify the selected runner and the durable state mount:

```bash
docker compose ps openresty fmu-runner fmu-runner-local
docker compose exec -T openresty id
stat -c '%u:%g %a %n' fmu-access-state
docker compose exec -T openresty sh -c '
  set -eu
  probe=/var/lib/openresty/fmu-access/.write-test-$$
  printf test > "$probe"
  rm -f "$probe"
  echo "OpenResty can write FMU access state"
'
```

The OpenResty UID/GID must match the owner of `fmu-access-state`. A successful
health check alone does not test this write path.

## Step 9 — Create the institutional wallet

1. Open `https://lab.your-institution.edu/wallet-dashboard`.
2. Enter the `ADMIN_ACCESS_TOKEN` from `.env`.
3. Click **Create wallet** or **Import wallet**.
4. Restart `blockchain-services` to load the wallet configuration:

```bash
docker compose restart blockchain-services
```

## Step 10 — Configure lab connections in Guacamole

See [Guacamole Connections](../configuring-lab-connections/guacamole-connections.md).

## Useful commands

```bash
# Stop everything
docker compose down

# Restart a single service
docker compose restart openresty

# Follow logs for one service
docker compose logs -f blockchain-services

# Force rebuild after code changes
docker compose up -d --build blockchain-services
```

## Next steps

- [NixOS installation](install-nixos.md)
- [End-to-end operator tutorial](../tutorials/tutorial-first-lab-session.md)
- [Operations and health](../reference/operations-and-health.md)
