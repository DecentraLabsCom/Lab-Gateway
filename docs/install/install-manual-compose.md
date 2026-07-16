# Installation Guide — Manual Docker Compose

Use this guide if you want full control over every configuration step without running
the interactive setup script.

## Prerequisites

| Requirement | Minimum version |
|---|---|
| Docker Engine (Linux) or Docker Desktop (Windows/macOS) | 20.10+ |
| Docker Compose | 2.0+ |
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
MYSQL_PASSWORD=legacy_migration_password
GUACAMOLE_MYSQL_PASSWORD=change_to_strong_password
BLOCKCHAIN_MYSQL_PASSWORD=change_to_strong_password
OPS_BACKEND_MYSQL_PASSWORD=change_to_strong_password
OPS_GUACAMOLE_MYSQL_PASSWORD=change_to_strong_password
GUACAMOLE_MYSQL_USER=guacamole_app
BLOCKCHAIN_MYSQL_USER=blockchain_app
OPS_BACKEND_MYSQL_USER=ops_backend
OPS_GUACAMOLE_MYSQL_USER=ops_guac

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
FEATURES_PROVIDERS_ENABLED=true
FEATURES_PROVIDERS_REGISTRATION_ENABLED=true

# Origins allowed by the blockchain service
ALLOWED_ORIGINS=https://lab.your-institution.edu,https://marketplace-decentralabs.vercel.app
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem
```

Leave `INSTITUTIONAL_WALLET_ADDRESS` and `INSTITUTIONAL_WALLET_PASSWORD` empty — they
are populated automatically after you create or import a wallet through the web console.

## Step 5 — Set file ownership (Linux/macOS only)

Find your UID and GID:

```bash
id -u && id -g
```

Set them in `.env`:

```env
HOST_UID=1000
HOST_GID=1000
```

Create and own the data directories:

```bash
mkdir -p blockchain-data certs
chown -R 1000:1000 blockchain-data certs
```

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

## Step 8 — Verify health

```bash
# Gateway routing layer
curl -k https://localhost/health

# Blockchain services
curl -k https://localhost/auth/.well-known/openid-configuration
```

Both should return JSON without errors. The public health response is intentionally redacted; Lab Manager operators can use `/health/details` with the configured `LAB_MANAGER_TOKEN` for backend diagnostics.

## Step 9 — Create the institutional wallet

1. Open `https://lab.your-institution.edu/wallet-dashboard`.
2. Enter the `ADMIN_ACCESS_TOKEN` from `.env`.
3. Click **Create wallet** or **Import wallet**.
4. Restart `blockchain-services` to load the wallet configuration:

```bash
docker compose restart blockchain-services
```

## Step 10 — Configure lab connections in Guacamole

See [Guacamole Connections](../../configuring-lab-connections/guacamole-connections.md).

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
