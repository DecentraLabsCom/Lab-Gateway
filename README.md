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

### ✅ Authentication Service (Spring Boot)
- **RESTful API**: Comprehensive authentication endpoints
- **Blockchain Integration**: Web3j for smart contract interaction
- **JWT Management**: Token validation and generation
- **Wallet Operations**: Create, import, and manage Ethereum wallets
- **Institutional Treasury**: Full treasury management with spending limits and period controls
- **Health Monitoring**: Built-in health checks and metrics

### ✅ Lab Access & Management
- **Apache Guacamole Integration**: Clientless RDP/VNC/SSH access through the browser
- **Session Cookie Management**: JTI-based session validation with automatic expiration
- **Header Propagation**: Authenticated username forwarded to Guacamole for auto-login
- **Ops Worker**: Remote power management for lab stations (Wake-on-LAN, shutdown)

## 🚀 Quick Deployment

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

### Manual Deployment

If you prefer manual configuration:

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   cp blockchain-services/.env.example blockchain-services/.env
   ```

2. **Edit `.env` and `blockchain-services/.env`** with your configuration (see Configuration section below)

3. **Add SSL certificates** to `certs/` folder:
   ```
   certs/
   ├── fullchain.pem      # SSL certificate chain
   ├── privkey.pem        # SSL private key
   └── public_key.pem     # JWT public key (from auth provider)
   ```

4. **Start the services:**
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

# Database Configuration
MYSQL_ROOT_PASSWORD=secure_password
MYSQL_DATABASE=guacamole_db
MYSQL_USER=guacamole_user
MYSQL_PASSWORD=db_password

# Guacamole
GUAC_ADMIN_USER=guacadmin
GUAC_ADMIN_PASS=secure_admin_password
AUTO_LOGOUT_ON_DISCONNECT=true
```

OpenResty and blockchain-services derive public URLs (issuer, OpenID metadata, etc.) from `SERVER_NAME` and `HTTPS_PORT`. If you ever need to override that computed value, set `BASE_DOMAIN` inside `blockchain-services/.env` or export it in the container's
environment. All authentication endpoints live under the fixed `/auth` base path to match both services.

##### Deployment modes: Direct vs Router forwarding

- **Direct (default)**: Gateway has a public IP or you're testing locally.
  ```bash
  docker compose up -d
  ```

- **Behind a router/NAT**: External traffic arrives via port forwarding (e.g., router:8043 → host:443). Set `HTTPS_PORT` to the **public port** (e.g., 8043) and use the router override:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.router.yml up -d
  ```
This binds to `0.0.0.0:443` and `0.0.0.0:80` so the router can reach the gateway.

Optional Cloudflare Tunnel settings (filled automatically if you opt in during setup):

```env
ENABLE_CLOUDFLARE=true
CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_tunnel_token_or_empty_for_quick_tunnel
```

#### Blockchain Service Configuration (`blockchain-services/.env`)

```env
# Smart Contract
CONTRACT_ADDRESS=0xYourSmartContractAddress

# Network RPC URLs (with failover support)
ETHEREUM_SEPOLIA_RPC_URL=https://rpc1.com,https://rpc2.com,https://rpc3.com

# Institutional Wallet (for automated transactions)
INSTITUTIONAL_WALLET_ADDRESS=0xYourWalletAddress
INSTITUTIONAL_WALLET_PASSWORD=YourSecurePassword

# Security
WALLET_ENCRYPTION_SALT=RandomString32CharsOrMore
ALLOWED_ORIGINS=https://your-frontend.com,https://marketplace.com
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace.com/.well-known/public-key.pem
```

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

* **Blockchain Services** (Spring Boot 3.x) - Authentication and wallet operations microservice
* **Web3j** - Ethereum blockchain integration library
* **JWT** - Generates authentication tokens with blockchain claims
* **Smart Contract Events** - Real-time blockchain monitoring

## 📁 Project Structure

```
lab-gateway/
├── 📁 openresty/           # Reverse proxy configuration
│   ├── nginx.conf          # Main Nginx configuration
│   ├── lab_access.conf     # Lab access routes
│   └── lua/                # Lua modules for auth and session management
├── 📁 guacamole/           # RDP/VNC/SSH client
│   └── extensions/         # Guacamole extensions
├── 📁 mysql/               # DB scripts and schemas
│   ├── 001-create-schema.sql
│   ├── 002-create-admin-user.sql
│   ├── 003-rdp-example.sql
│   └── 004-auth-service-schema.sql
├── 📁 web/                 # Web frontend (optional)
├── 📁 blockchain-services/ # Blockchain auth & wallet service (Git submodule)
├── 📁 blockchain-data/     # Encrypted wallet persistence (not in git)
├── 📁 certs/               # SSL certificates (not in git)
├── 📁 tests/               # Gateway tests (unit + smoke)
│   ├── smoke/              # End-to-end smoke tests
│   └── unit/               # Lua unit tests
├── 📄 docker-compose.yml   # Service orchestration
├── 📄 .env.example         # Configuration template
├── 📄 setup.sh/.bat        # Installation scripts
└── 📄 update-blockchain-services.sh/.bat  # Submodule update scripts
```

## 🧪 Testing

### Gateway Tests

Unit tests cover the OpenResty gateway logic (Lua handlers and session guard). They run via the OpenResty container so you do not need a local Lua installation:

```bash
# Windows (PowerShell)
docker run --rm -v "${PWD}:/workspace" -w /workspace openresty/openresty:alpine-fat luajit openresty/tests/run.lua

# Linux/macOS
docker run --rm -v "$(pwd):/workspace" -w /workspace openresty/openresty:alpine-fat luajit openresty/tests/run.lua
```

The command executes every spec under `openresty/tests/unit/` through a lightweight Lua test runner.

### Smoke Tests

For an end-to-end smoke check (OpenResty ↔ Guacamole proxy logic):

```bash
cd tests/smoke
./run-smoke.sh
```

The script spins up a miniature docker-compose environment with mock services, validates that JWT cookies are issued, and ensures Guacamole receives the propagated `Authorization` header.

### Coverage Reports

To collect LuaCov coverage metrics:

```bash
# Windows (PowerShell)
docker run --rm -v "${PWD}:/workspace" -w /workspace openresty/openresty:alpine-fat sh -c "luarocks install luacov >/dev/null && luajit -lluacov openresty/tests/run.lua && luacov"

# Linux/macOS
docker run --rm -v "$(pwd):/workspace" -w /workspace openresty/openresty:alpine-fat sh -c "luarocks install luacov >/dev/null && luajit -lluacov openresty/tests/run.lua && luacov"
```

Coverage data will be written to `luacov.report.out` and `luacov.stats.out`.

## 🛠️ Development

### Local Development Setup

1. **Start services in development mode:**
   ```bash
   docker compose up -d
   ```

2. **Access services:**
   - Blockchain Services: http://localhost:8080/wallet (or configured port)
   - Guacamole: https://localhost:8443/guacamole
   - MySQL: localhost:3306

### Debugging

Enable debug logging in `.env` or `blockchain-services/.env`:
```env
LOG_LEVEL_AUTH=DEBUG
LOG_LEVEL_SECURITY=DEBUG
LOG_LEVEL_WEB=DEBUG
```

View logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f openresty
docker compose logs -f blockchain-services
docker compose logs -f guacamole
```

## 🤝 Contributing

1. **Fork** the project
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

## 📝 Documentation

- **Main Documentation**: This README (for main branch - full version)
- **Logging**: [LOGGING.md](LOGGING.md) - Log configuration and management
- **Guacamole Setup**: [configuring-lab-connections/guacamole-connections.md](configuring-lab-connections/guacamole-connections.md)
- **Blockchain Services**: Check [blockchain-services/README.md](blockchain-services/README.md) for detailed API documentation

## 📞 Support

* **Issues**: [GitHub Issues](https://github.com/DecentraLabsCom/lite-lab-gateway/issues)
* **Logs**: Use `docker compose logs [service]` for troubleshooting
* **Configuration**: Review `.env.example` and `blockchain-services/.env.example` for all options

---

*DecentraLabs Gateway provides a complete, production-ready blockchain authentication system for decentralized laboratory access.*
