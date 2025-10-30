# Lab Gateway Overview

Lab Gateway is a laboratory virtualization solution that enables remote access to lab environments. It's available in two versions with different levels of features and authentication.

## 📋 Available Versions

### Lite Version (Branch `lite`)

Basic version with essential features:

* ✅ RDP/VNC/SSH access to lab computers
* ✅ Intuitive web interface
* ✅ Auth through input JWTs
* ✅ Reverse proxy with OpenResty
* ✅ MySQL database for Guacamole configuration
* ✅ Complete containerization with Docker
* ✅ Simple configuration

**Ideal for**: Development environments, personal testing, quick deployments.

### Full Version (Branch `full`)

Complete version with advanced blockchain-based authentication and wallet operations:

* ✅ All Lite version features
* ✅ **Blockchain Services Integration** (Spring Boot microservice)
* ✅ **JWT Generation**: Issues and processes secure tokens with blockchain claims
* ✅ **Redis Caching**: Performance optimization for blockchain queries
* ✅ **Wallet Support**: Ethereum wallet support for blockchain actions and features
* ✅ **Smart Contract Authorization**: Validates lab reservation requests on-chain
* ✅ **Institutional Treasury Management**: Deposit or withdraw funds from the institutional treasury, set user spending limits, etc.
* ✅ **Event Listening**: Real-time monitoring of contract events
* ✅ **Transaction Signing**: Programmatic transaction capabilities
* ✅ **RESTful APIs**: Comprehensive authentication endpoints

**Ideal for**: Production environments, enterprise deployments, maximum security, management and decentralization.

## 🚀 Quick Start

### Select Version

```bash
# Clone the repository
git clone https://github.com/DecentraLabsCom/lite-lab-gateway.git
cd lite-lab-gateway

# Switch to desired version
git switch lite    # For basic version
# or
git switch full    # For complete version
```

### Configuration and Installation

Each version includes its own detailed documentation:

* **Lite Version**: See [LITE-VERSION.md](LITE-VERSION.md)
* **Full Version**: See [FULL-VERSION.md](FULL-VERSION.md)

## 🔄 Detailed Comparison

| Feature                      | Lite | Full |
| ---------------------------- | ---- | ---- |
| **RDP Access**               | ✅    | ✅    |
| **Web Interface**            | ✅    | ✅    |
| **Docker Compose**           | ✅    | ✅    |
| **MySQL + Guacamole**        | ✅    | ✅    |
| **OpenResty Proxy**          | ✅    | ✅    |
| **AuthX Through JWT**        | ✅    | ✅    |
| **Blockchain Authorization** | ❌    | ✅    |
| **JWT Generation**           | ❌    | ✅    |
| **Redis Session Store**      | ❌    | ✅    |
| **Wallet Support**           | ❌    | ✅    |
| **Institutional Treasury Mgt**| ❌    | ✅    |
| **Event Listening**          | ❌    | ✅    |
| **Transaction Signing**      | ❌    | ✅    |
| **On-Chain Reservation Validation** | ❌    | ✅    |

## Requirements

### System Requirements

**Operating System:**
- Linux (recommended) - Ubuntu 20.04+, Debian 11+, CentOS 8+
- Unix-like systems (BSD, macOS) - supported
- Windows - via WSL2 or Docker Desktop

**Hardware (Minimum):**
- 2 CPU cores
- 4GB RAM
- Network interface with internet connectivity

**Software:**
- **Docker Engine 20.10+** (Linux) or **Docker Desktop** (Windows/macOS)
- **OpenSSL** (for certificate management)

### Network Requirements

The Lab Gateway requires network connectivity to:
1. **External Users** - To accept incoming HTTP(s) connections
2. **Internal Laboratory Servers** - To proxy RDP/VNC/SSH connections

This can be achieved through various network topologies:

#### Option A: Dual Network Interface (Most Secure)
```
Internet ──> [NIC1: Public IP] Lab Gateway [NIC2: Private IP] ──> Lab Network
```
- ✅ Two physical or virtual Network Interface Cards (NICs)
- ✅ Physical network isolation between public and lab networks
- ✅ Highest security level
- ❌ Requires specific hardware/VM configuration

#### Option B: Single Network Interface (Most Common)
```
Internet ──> Router/Firewall ──> [NIC: Private IP] Lab Gateway ──> Lab Servers
```
- ✅ Single NIC with routing configuration
- ✅ Works with cloud providers (AWS, Azure, GCP, DigitalOcean, etc.)
- ✅ Works with CDN/proxies (CloudFlare, CloudFront, etc.)
- ✅ Works with VPS/dedicated servers
- ✅ Labs accessed via private IPs, VPN tunnels, or localhost
- ✅ Most flexible and commonly deployed

#### Option C: VLAN Segmentation (Enterprise)
```
Internet ──> [NIC with VLAN tagging] Lab Gateway ──> VLAN 10 / VLAN 20
```
- ✅ Single NIC with 802.1Q VLAN tagging
- ✅ Logical separation of public and lab traffic
- ✅ Common in enterprise/datacenter environments

#### Option D: Localhost/Docker (Development/Testing)
```
Lab Gateway (Docker) ──> host.docker.internal ──> Local Labs
```
- ✅ Labs running on the same machine
- ✅ Labs in Docker containers
- ✅ Ideal for development and testing

**Required Network Connectivity:**
- **Inbound**: HTTPS (443 or custom port), HTTP (80 for redirects)
- **Outbound to Labs**: RDP (3389), VNC (5900-5910), SSH (22)
- **Outbound to Database**: MySQL (3306) - if external
- **DNS Resolution**: For lab server names (or static hosts file)

**Recommended for Production:**
- Static public IP or Dynamic DNS
- Valid SSL certificate (Let's Encrypt supported)
- Firewall properly configured
- Network monitoring tools

### SSL/TLS Certificates

**Development:**
- Self-signed certificates (auto-generated by setup scripts)
- Valid for localhost testing

**Production:**
- Valid SSL certificate from trusted CA
- Let's Encrypt (free, automated renewal)
- Commercial certificate providers
- Wildcard certificates for multiple subdomains

Required files in `certs/` directory:

## �️ Technology Stack

### Core Components (Both Versions)

* **OpenResty** - Reverse proxy and load balancer
* **Apache Guacamole** - RDP/VNC gateway
* **MySQL** - Primary database
* **Docker** - Containerization platform (includes Compose)

### Full Version Additions

* **Blockchain Services** (Spring Boot) - Authentication and wallet operations microservice
* **Web3j** - Ethereum blockchain integration
* **Redis** - Session store and cache
* **JWT** - Generates authentication tokens with blockchain claims
* **Smart Contract Events** - Real-time blockchain monitoring

## � Project Structure

```
lab-gateway/
├── 📁 openresty/          # Reverse proxy configuration
├── 📁 guacamole/          # RDP/VNC client
├── 📁 mysql/              # DB scripts and schemas
├── 📁 web/                # Web frontend
├── 📁 blockchain-services/# Blockchain auth & wallet service (full version only)
├── 📁 certs/              # SSL certificates (if created by setup)
├── 📄 docker-compose.yml  # Service orchestration
├── 📄 .env.example        # Configuration template
└── 📄 setup.sh/.bat       # Installation scripts
```

## 🤝 Contributing

1. **Fork** the project
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

## � Support

* **Issues**: [GitHub Issues](https://github.com/DecentraLabsCom/lite-lab-gateway/issues)
* **Documentation**: Check LITE-VERSION.md or FULL-VERSION.md according to your version

***

> **Note**: This README serves as a navigation hub. For specific installation and configuration instructions, check the documentation for each version.
