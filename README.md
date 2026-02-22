# 🚀 DecentraLabs Gateway
[![Gateway Tests](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/gateway-tests.yml/badge.svg)](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/gateway-tests.yml)
[![Security Scan](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/security.yml/badge.svg)](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/security.yml)
[![Release](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/release.yml/badge.svg)](https://github.com/DecentraLabsCom/lite-lab-gateway/actions/workflows/release.yml)

## 🎯 Overview

DecentraLabs Gateway provides a complete blockchain-based authentication system for laboratory access. It includes all components needed for a decentralized lab access solution with advanced features, wallet management, and institutional treasury operations.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌───────────────────┐
│   User Wallet   │    │  OpenResty      │    │Blockchain Services│
│   or JWT        ├────┤  (Nginx + Lua)  ├────┤   (Spring Boot)   │
└─────────────────┘    └─────────────────┘    └───────────────────┘
                                │                        │
                                │                        │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Guacamole     │    │   Blockchain    │
                       │  (Lab Access)   │    │   (Smart        │
                       └─────────────────┘    │   Contracts)    │
                                │             └─────────────────┘
                                │                        
                       ┌─────────────────┐
                       │     MySQL       │
                       │   (Database)    │
                       └─────────────────┘
```

## 🌟 Features

### ✅ Blockchain Authentication
- **Flexible Signature Verification**: Users authenticate using their crypto wallet or SSO credentials in an external trusted system that emits a signed JWT
- **Smart Contract Integration**: Validates users' lab reservations on-chain
- **JWT Token Generation**: Issues secure access tokens for lab sessions (to be consumed by Guacamole)

### ✅ Blockchain Services (Spring Boot)
- **RESTful API**: Comprehensive authentication endpoints
- **Blockchain Integration**: Web3j for smart contract interaction
- **JWT Management**: Token validation and generation
- **Wallet Operations**: Create, import, and manage Ethereum wallets
- **Institutional Treasury**: Full treasury management with spending limits and period controls
- **Health Monitoring**: Built-in health checks and metrics

### ✅ Lab Access & Management (OpenResty & Guacamole)
- **Apache Guacamole Integration**: Clientless RDP/VNC/SSH access through the browser
- **Session Cookie Management**: JTI-based session validation with automatic expiration
- **Header Propagation**: Authenticated username forwarded to Guacamole for auto-login
- **Ops Worker**: Remote power management for lab stations (Wake-on-LAN, shutdown)

## 🚀 Quick Deployment

### Choose an Installation Mode

Use one of these modes depending on your target:

1. **Setup Scripts (`setup.sh` / `setup.bat`)**  
   Best for first-time installs. It prepares env files, secrets, and can start the full stack.

2. **Manual Docker Compose**  
   Best if you want full control over compose commands and deployment flow.

3. **NixOS Compose-managed Host (`nixos-rebuild --flake ...#gateway`)**  
   Best for dedicated NixOS hosts where you want declarative system + service management.

### Using Setup Scripts (Recommended)

The setup scripts will automatically:
- ✅ Check Docker, Docker Compose, and Git prerequisites
- ✅ Initialize/refresh the `blockchain-services` submodule and env files
- ✅ Configure environment variables (database, domain, blockchain, CORS)
- ✅ Generate database passwords
- ✅ Create the `blockchain-data/` directory for wallet persistence
- ✅ Optionally start every container with `docker compose up -d`
- ✅ Ask if you want to enable a Cloudflare Tunnel so the gateway is reachable without a public IP/DNS
- ✅ Configure Guacamole admin credentials
- ✅ Generate OPS worker secret for lab power operations
- ☑️ Remind you to create/import the institutional wallet later from the blockchain-services web console

**Windows:**
```cmd
setup.bat
```

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

That's it! The script will guide you through the setup and start all services automatically.

### NixOS Deployment

This repository also includes a `flake.nix` with:

- `nixosModules.default`: NixOS module to manage the stack through systemd
- `nixosModules.gateway-host`: host defaults for a dedicated NixOS gateway machine
- `nixosConfigurations.gateway`: complete host config ready for `nixos-rebuild`

#### NixOS host configuration (compose-managed)

This mode is only for NixOS machines.

Use the module directly (example):

```nix
{
  inputs.lab-gateway.url = "path:/srv/lab-gateway";

  outputs = { nixpkgs, lab-gateway, ... }: {
    nixosConfigurations.gateway = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        lab-gateway.nixosModules.default
        {
          services.lab-gateway = {
            enable = true;
            projectDir = "/srv/lab-gateway";
            envFile = "/srv/lab-gateway/.env";
            # profiles = [ "cloudflare" ];
          };
        }
      ];
    };
  };
}
```

Then apply it:

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
```

Complete host flow (real machine):

```bash
# 1) Put this repo on the target NixOS host
sudo mkdir -p /srv
sudo git clone https://github.com/DecentraLabsCom/lite-lab-gateway.git /srv/lab-gateway
cd /srv/lab-gateway

# 2) Prepare env files
sudo cp .env.example .env
sudo cp blockchain-services/.env.example blockchain-services/.env

# 3) Edit values (passwords, domain, tokens, RPC, contract address)
sudo nano .env
sudo nano blockchain-services/.env

# 4) Apply the full NixOS configuration shipped by this flake
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway

# 5) Validate the service
systemctl status lab-gateway.service
```

`blockchain-services/.env` must still exist under `projectDir`, because `docker-compose.yml` references it directly.

`nixosConfigurations.gateway` imports your existing `/etc/nixos/configuration.nix` and layers the gateway module on top, so host-specific settings (bootloader, users, disks, hardware) are preserved.
Host-level values (hostname, timezone, firewall, profiles, SSH hardening) are installation-specific and should be overridden per environment.

### Manual Deployment

If you prefer manual configuration:

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   cp blockchain-services/.env.example blockchain-services/.env
   ```

2. **Edit `.env` and `blockchain-services/.env`** with your configuration (see Configuration section below)
  - Configure the two gateway access tokens for production:
    - `TREASURY_TOKEN`: protects wallet/treasury routes (`/wallet`, `/treasury`, `/wallet-dashboard`, `/treasury/admin/**`)
    - `LAB_MANAGER_TOKEN`: protects `/lab-manager` and `/ops` from public networks

3. **Set host UID/GID for bind mounts (Linux/macOS)** so containers can write to `certs/` and `blockchain-data/`:
   ```bash
   # Choose the user that will own the folders
   id -u
   id -g
   ```
   Then set in `.env` (use `0`/`0` if you run everything as root):
   ```env
   HOST_UID=1000
   HOST_GID=1000
   ```
   Ensure the folders are owned by that user:
   ```bash
   chown -R 1000:1000 certs blockchain-data
   ```

4. **Add SSL certificates** to `certs/` folder:
   ```
   certs/
   ├── fullchain.pem      # SSL certificate chain
   ├── privkey.pem        # SSL private key
   └── public_key.pem     # JWT public key (optional if blockchain-services generates it)
   ```

   `public_key.pem` is generated automatically by `blockchain-services` on first start
   when missing. You only need to provide it manually if you use an external auth signer.

   **Database schema:** When `blockchain-services` has a MySQL datasource configured, it runs Flyway
   migrations on startup to create the auth, WebAuthn, and intents tables automatically.

5. **Start the services:**
   ```bash
   docker compose up -d --build
   ```

## ⚙️ Configuration

### 🔧 Environment Variables

The gateway uses **modular configuration** with separate `.env` files:

- **`.env`** - Gateway-specific configuration (server, database, Guacamole)
- **`blockchain-services/.env`** - Blockchain service configuration (contracts, wallets, RPC)

This separation keeps concerns isolated and makes the blockchain service independently configurable.

#### Gateway Configuration (`.env`)

```env
# Basic Configuration
SERVER_NAME=yourdomain.com
HTTPS_PORT=443
HTTP_PORT=80

# OpenResty bind address (127.0.0.1 for local-only, 0.0.0.0 for public)
OPENRESTY_BIND_ADDRESS=0.0.0.0
# OpenResty bind ports (local ports on the host)
OPENRESTY_BIND_HTTPS_PORT=443
OPENRESTY_BIND_HTTP_PORT=80

# Host UID/GID for bind mounts (Linux/macOS)
HOST_UID=1000
HOST_GID=1000

# Database Configuration
MYSQL_ROOT_PASSWORD=secure_password
MYSQL_DATABASE=guacamole_db
MYSQL_USER=guacamole_user
MYSQL_PASSWORD=db_password
BLOCKCHAIN_MYSQL_DATABASE=blockchain_services

# Guacamole
GUAC_ADMIN_USER=guacadmin
GUAC_ADMIN_PASS=secure_admin_password
AUTO_LOGOUT_ON_DISCONNECT=true

# OpenResty CORS allowlist (comma-separated, optional)
CORS_ALLOWED_ORIGINS=https://your-frontend.com,https://marketplace.com

# Lab Manager + Ops Worker
LAB_MANAGER_TOKEN=your_lab_manager_token
LAB_MANAGER_TOKEN_HEADER=X-Lab-Manager-Token
LAB_MANAGER_TOKEN_COOKIE=lab_manager_token

# Blockchain Services remote access
TREASURY_TOKEN=your_treasury_token
TREASURY_TOKEN_HEADER=X-Access-Token
TREASURY_TOKEN_COOKIE=access_token
TREASURY_TOKEN_REQUIRED=true
SECURITY_ALLOW_PRIVATE_NETWORKS=true
ADMIN_DASHBOARD_ALLOW_PRIVATE=true

# Certbot / ACME (optional - for Let's Encrypt automation)
CERTBOT_DOMAINS=yourdomain.com,www.yourdomain.com
CERTBOT_EMAIL=you@example.com
CERTBOT_STAGING=0
```

Use a strong `GUAC_ADMIN_PASS`. Common defaults are rejected at startup to avoid insecure deployments. The same check applies to `MYSQL_ROOT_PASSWORD` and `MYSQL_PASSWORD` (defaults like `CHANGE_ME` will stop MySQL from initializing). Set a strong `LAB_MANAGER_TOKEN` (or leave it empty to keep `/ops` disabled and `/lab-manager` private-network-only). Set `TREASURY_TOKEN` to protect wallet/treasury endpoints exposed through OpenResty for remote access.

`blockchain-services` uses a dedicated schema named `blockchain_services` by default. If you want a different name, set `BLOCKCHAIN_MYSQL_DATABASE` in `.env`.

OpenResty and blockchain-services derive public URLs (issuer, OpenID metadata, etc.) from `SERVER_NAME` and `HTTPS_PORT`. If you ever need to override that computed value, set `BASE_DOMAIN` inside `blockchain-services/.env` or export it in the container's
environment. All authentication endpoints live under the fixed `/auth` base path to match both services.

##### Deployment modes: Direct vs Router forwarding

- **Direct (default)**: Gateway has a public IP or you're testing locally.
  - Local-only access: `OPENRESTY_BIND_ADDRESS=127.0.0.1`
  - Public access: `OPENRESTY_BIND_ADDRESS=0.0.0.0`
  - If you change `HTTPS_PORT`/`HTTP_PORT`, also set `OPENRESTY_BIND_HTTPS_PORT`/`OPENRESTY_BIND_HTTP_PORT` to the same values.
  ```bash
  docker compose up -d
  ```

- **Behind a router/NAT**: External traffic arrives via port forwarding (e.g., router:8043 -> host:443).
  Set `OPENRESTY_BIND_ADDRESS=0.0.0.0`.
  - Public port (what clients use): `HTTPS_PORT=8043`
  - Local bind port (what the host listens on): `OPENRESTY_BIND_HTTPS_PORT=443`
  ```bash
  docker compose up -d
  ```

Optional Cloudflare Tunnel settings (filled automatically if you opt in during setup):

```env
CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_tunnel_token_or_empty_for_quick_tunnel
```
Runtime activation requires Compose profiles (`--profile cloudflare` or `--profile cloudflare-token`).

#### Blockchain Service Configuration (`blockchain-services/.env`)

```env
# Smart Contract
CONTRACT_ADDRESS=0xYourSmartContractAddress
TREASURY_ADMIN_DOMAIN_VERIFYING_CONTRACT=0xYourSmartContractAddress

# Network RPC URLs (with failover support)
RPC_URL=https://1rpc.io/sepolia
ETHEREUM_SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com,https://0xrpc.io/sep,https://ethereum-sepolia-public.nodies.app

# Institutional Wallet (for automated transactions)
INSTITUTIONAL_WALLET_ADDRESS=0xYourWalletAddress
INSTITUTIONAL_WALLET_PASSWORD=YourSecurePassword

# Security
WALLET_ALLOWED_ORIGINS=https://gateway.example.com
ALLOWED_ORIGINS=https://your-frontend.com,https://marketplace.com
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace.com/.well-known/public-key.pem
```

#### Access Controls (Important)

- `/wallet-dashboard`, `/wallet`, `/treasury`: require `TREASURY_TOKEN` for non-private clients. If the token is unset, access is limited to loopback/Docker networks. The token is provided automatically via the authentication modal on the gateway's homepage, which stores it locally and adds it as the `X-Access-Token` header on all requests.
- `/treasury/admin/**`: uses `TREASURY_TOKEN` only (header/cookie/query parameter). If `TREASURY_TOKEN` is unset, access is limited to loopback/Docker ranges.
- `/treasury/admin/execute`: additionally requires an EIP-712 signature from the institutional wallet, including a fresh timestamp.
- **Initial setup**: Click "Wallet & Treasury→" from the homepage, enter your `TREASURY_TOKEN` when prompted. The token will be stored in your browser and automatically included in all requests.
- `/lab-manager`: allows private networks by default; requires `LAB_MANAGER_TOKEN` for non-private clients. Click "Lab Manager→" from the homepage and enter your token when prompted.
- `/ops`: **network-restricted** to `127.0.0.1` and `172.16.0.0/12` only, plus requires `LAB_MANAGER_TOKEN`. Lab Manager UI works remotely, but ops features (WoL, WinRM, heartbeat) require access from the gateway server or institution network.
- If wallet actions return `JSON.parse` errors in the browser, ensure both `CORS_ALLOWED_ORIGINS` and `WALLET_ALLOWED_ORIGINS` include your gateway origin.

## Institutional Wallet Setup

The institutional wallet is managed automatically by blockchain-services:

1. **First-time setup**: Create or import the wallet via:
   - Web console: `https://localhost:8443/wallet-dashboard` (or `https://your-domain/wallet-dashboard`)
   - Or API: Call `/wallet/create` or `/wallet/import` endpoints

2. **Automatic configuration**: After creation/import, blockchain-services automatically:
   - Stores the encrypted wallet in `blockchain-data/wallets.json`
   - Writes credentials to `blockchain-data/wallet-config.properties`
   - Loads the wallet on every restart using the stored configuration

3. **Manual override (optional)**: Only needed if using external secret management:
   ```env
   # In blockchain-services/.env - leave empty for automatic configuration
   INSTITUTIONAL_WALLET_ADDRESS=  # Auto-configured from wallet-config.properties
   INSTITUTIONAL_WALLET_PASSWORD= # Auto-configured from wallet-config.properties
   ```

The encrypted wallet and configuration files are stored in `blockchain-data/` which is mounted as a Docker volume and excluded from git.

## 💻 System Requirements

**Operating System:**
- Linux (recommended) - Ubuntu 20.04+, Debian 11+, CentOS 8+
- Unix-like systems (BSD, macOS) - supported
- Windows - via WSL2 or Docker Desktop

**Hardware (Minimum):**
- 2 CPU cores
- 4GB RAM
- 20GB disk space (including Docker images and logs)
- Network interface with internet connectivity

**Software:**
- **Docker Engine 20.10+** (Linux) or **Docker Desktop** (Windows/macOS)
- **Docker Compose 2.0+** (included with Docker Desktop)

### Network Requirements

The Lab Gateway requires network connectivity to:
1. **External Users** - To accept incoming HTTP(s) connections
2. **Internal Laboratory Servers** - To proxy RDP/VNC/SSH connections

This can be achieved through various network topologies:

#### Option A: Dual Network Interface (Most Secure)
```
Internet ──> [NIC1: Public IP] Lab Gateway [NIC2: Private IP] ──> Lab Computers
```
- ✅ Two physical or virtual Network Interface Cards (NICs)
- ✅ Physical network isolation between public and lab networks
- ✅ Highest security level
- ❌ Requires specific hardware/VM configuration

#### Option B: Single Network Interface (Most Common)
```
Internet ──> Router/Firewall ──> [NIC: Private IP] Lab Gateway ──> Lab Computers
```
- ✅ Single NIC with routing configuration
- ✅ Works with cloud providers (AWS, Azure, GCP, DigitalOcean, etc.)
- ✅ Works with CDN/proxies (CloudFlare, CloudFront, etc.)
- ✅ Works with VPS/dedicated servers
- ✅ Labs accessed via private IPs or VPN tunnels
- ✅ Most flexible and commonly deployed

#### Option C: VLAN Segmentation (Enterprise)
```
Internet ──> [NIC with VLAN tagging] Lab Gateway ──> VLAN 10 / VLAN 20
```
- ✅ Single NIC with 802.1Q VLAN tagging
- ✅ Logical separation of public and lab traffic
- ✅ Common in enterprise/datacenter environments

## 🌐 Remote Access without Public IP (Cloudflare Tunnel)

- Enable the Cloudflare Tunnel option during `setup.sh` / `setup.bat` to spin up the `cloudflared` sidecar (Compose profile `cloudflare`) and expose the gateway without opening inbound ports.
- Works behind campus/corporate NAT as long as outbound HTTPS (443) is allowed; WebSockets for Guacamole are supported through the tunnel.
- Token mode: paste a Cloudflare Tunnel token from your Zero Trust dashboard and Cloudflare will publish the hostname in your zone.
- Quick Tunnel mode: leave the token empty and a random `*.cfargotunnel.com` hostname will appear in `docker compose --profile cloudflare logs cloudflared`.
- Start/stop with the profile when needed: `docker compose --profile cloudflare up -d` / `docker compose --profile cloudflare down`.

## 🔐 SSL/TLS Certificates

**Development:**
- Self-signed certificates (auto-generated)
- Valid for localhost testing

**Production:**
- Valid SSL certificate from trusted CA
- Let's Encrypt (free, automated renewal)
- Commercial certificate providers
- Wildcard certificates for multiple subdomains

## 🛠️ Technology Stack

### Core Components

* **OpenResty** - Reverse proxy and load balancer with Lua scripting
* **Apache Guacamole** - Clientless remote desktop gateway (RDP/VNC/SSH)
* **MySQL 8.0** - Primary database for configuration and user data
* **Docker** - Containerization platform with Compose orchestration

### Blockchain Integration

* **Blockchain Services** (Spring Boot 4.x) - Authentication and wallet operations microservice
* **Web3j** - Ethereum blockchain integration library
* **JWT** - Generates authentication tokens with blockchain claims
* **Smart Contract Events** - Real-time blockchain monitoring

## 📁 Project Structure

```
lab-gateway/
├── 📄 flake.nix                 # Nix flake outputs (NixOS config/module)
├── 📄 docker-compose.yml        # Main service orchestration
├── 📄 .env.example              # Gateway configuration template
├── 📄 setup.sh / setup.bat      # Guided setup scripts
├── 📄 selfsigned-refresh.sh     # Self-signed cert helper
├── 📁 nix/
│   ├── nixos-module.nix         # services.lab-gateway (compose-managed) module
│   └── hosts/gateway.nix        # Host defaults for nixosConfigurations.gateway
├── 📁 blockchain-services/       # Blockchain auth/wallet service (submodule)
├── 📁 openresty/                # Reverse proxy (Nginx + Lua)
│   ├── nginx.conf
│   ├── lab_access.conf
│   ├── lua/
│   └── tests/                   # Lua unit test runner/specs
├── 📁 guacamole/                # Guacamole image customizations
├── 📁 mysql/                    # DB bootstrap and schema scripts
├── 📁 ops-worker/               # Lab station operations API worker
├── 📁 web/                      # Static frontend assets/pages
├── 📁 certbot/                  # ACME webroot/support files
├── 📁 tests/
│   ├── smoke/                   # End-to-end smoke tests
│   └── integration/             # Integration tests with mocks
├── 📁 docs/                     # Install guides, eduGAIN integration, and provider tutorials
├── 📁 certs/                    # Runtime certificates/keys (not in git)
├── 📁 blockchain-data/          # Runtime wallet/provider data (not in git)
└── 📁 configuring-lab-connections/ # Guacamole connection setup docs
```

`certs/` and `blockchain-data/` are runtime directories and may not exist until first setup.
`blockchain-services/` is a Git submodule and must be initialized/updated before running the stack.

## 🤝 Contributing

1. **Fork** the project
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request
