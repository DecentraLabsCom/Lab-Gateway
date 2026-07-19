# Installation Guide — Setup Script (Recommended)

The setup script is the fastest way to get Lab Gateway running. It handles prerequisites,
configuration files, secrets, and container startup in a single interactive session.

## Prerequisites

Install Docker/Compose, Git, and Python 3. Python 3 is used by the setup script
to migrate the SAML environment configuration before the containers start.

| Requirement | Minimum version |
|---|---|
| Docker Engine (Linux) or Docker Desktop (Windows/macOS) | 20.10+ |
| Docker Compose | 2.0+ (included with Docker Desktop) |
| Git | any recent version |
| Python | 3.x |
| 2 CPU cores, 4 GB RAM, 20 GB free disk | — |

Verify Docker is working before running the script:

```bash
docker --version
docker compose version
```

## Step 1 — Clone the repository

```bash
git clone https://github.com/DecentraLabsCom/Lab-Gateway.git Lab-Gateway
cd Lab-Gateway
```

On Windows, clone to a path without spaces, for example `C:\lab-gateway`.

## Step 2 - Optional: add production TLS certificates

If you already have a certificate for the gateway domain, copy it into `certs/`
before running setup:

```bash
mkdir -p certs
cp /path/to/fullchain.pem certs/fullchain.pem
cp /path/to/privkey.pem certs/privkey.pem
chmod 700 certs
chmod 600 certs/privkey.pem
chmod 644 certs/fullchain.pem
```

The setup script detects `certs/fullchain.pem` and `certs/privkey.pem`.
If you skip this step, OpenResty generates self-signed certificates for
development/local testing.

If you add or replace these files after the stack is running, restart OpenResty:

```bash
docker compose restart openresty
```

## Step 3 - Run the setup script

**Linux / macOS:**

```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**

```cmd
setup.bat
```

## Step 4 - Answer the interactive prompts

The script will guide you through the following steps automatically:

1. **Checks prerequisites** — Docker, Compose, and Git availability.
2. **Initialises submodules** — Pulls `blockchain-services` if it was not cloned recursively.
3. **Creates `.env` and `blockchain-services/.env`** — Copies the bundled templates.
4. **Asks for your domain name** — Used in TLS, CORS, and OIDC issuer configuration.
5. **Generates database passwords** — Random strong values are written directly to `.env`.
6. **Asks for Guacamole admin credentials** — Username and password for the remote-desktop admin panel.
7. **Asks about Cloudflare Tunnel** — Optional; use this if the server does not have a public IP.
8. **Starts the stack** — Runs `docker compose up -d` with all containers.

## Step 5 - Verify the stack is running

```bash
docker compose ps
```

Core containers should show `Up`; optional profiles such as `fmu-runner`,
`aas`, `certbot` or Cloudflare may be intentionally absent. Check the gateway
health endpoint:

```bash
curl -k https://localhost/health
```

The response is the detailed `blockchain-services` health document. A healthy
stack reports `status: "UP"`; `DEGRADED` means a queue, database or dependency
check needs attention even though the HTTP endpoint is reachable.

```json
{"status":"UP","service":"blockchain-services"}
```

## Step 6 - Set up the institutional wallet

1. Open `https://your-domain/wallet-dashboard` in a browser.
2. Enter your `ADMIN_ACCESS_TOKEN` (set in `.env`) when prompted.
3. Click **Create wallet** (new institution) or **Import wallet** (existing key).
4. The encrypted wallet is stored in `blockchain-data/wallets.json` and loaded automatically on every restart.

## Step 7 - Add your blockchain configuration

Edit `blockchain-services/.env` and set:

```env
CONTRACT_ADDRESS=0xYourDeployedContractAddress
ETHEREUM_SEPOLIA_RPC_URL=https://your-rpc-node
INSTITUTIONAL_WALLET_ADDRESS=  # leave empty — auto-filled after wallet creation
INSTITUTIONAL_WALLET_PASSWORD= # leave empty — auto-filled after wallet creation
ALLOWED_ORIGINS=https://your-domain.com
```

Restart the blockchain-services container to apply:

```bash
docker compose restart blockchain-services
```

## Step 8 - Configure a lab connection in Guacamole

See [Guacamole Connections](../../configuring-lab-connections/guacamole-connections.md) for the
full step-by-step guide on adding RDP/VNC connections to your physical lab computers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Container exits immediately | Run `docker compose logs <service>` to see the error. |
| MySQL fails to start | Check that passwords in `.env` are not set to default placeholder values (`CHANGE_ME`). |
| `curl /health` returns TLS error | Add `-k` for self-signed certs in development. In production, verify certificates in `certs/`. |
| Wallet dashboard asks for token repeatedly | Ensure `ADMIN_ACCESS_TOKEN` in `.env` is set and the browser is not blocking cookies. |

## Next steps

- [Configure lab connections](../../configuring-lab-connections/guacamole-connections.md)
- [Manual Docker Compose installation](install-manual-compose.md)
- [End-to-end operator tutorial](../tutorials/tutorial-first-lab-session.md)
