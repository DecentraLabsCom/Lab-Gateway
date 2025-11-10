# 🚀 DecentraLabs Gateway - Full Version

## 🎯 Overview

The Full Version of DecentraLabs Gateway provides a complete blockchain-based authentication system for laboratory access. It includes all components needed for a decentralized lab access solution with advanced features and monitoring.

## 🔀 Version Information

You are currently on the **Full Version** branch. This project offers two versions:

### 🚀 **Full Version** (Current Branch)
- **Purpose**: Complete blockchain-based authentication system
- **Components**: Blockchain Services (Spring Boot) + OpenResty + Guacamole + MySQL
- **Authentication**: Blockchain wallet signature verification or signed JWT verification + blockchain smart contract checks
- **Features**: Wallet-based auth, smart contract integration
- **Use Case**: Complete decentralized lab access solution
- **Benefits**: Maximum security and blockchain integration

### 🪶 **Lite Version**
- **Purpose**: JWT-validated gateway for lab access
- **Components**: OpenResty + Guacamole + MySQL
- **Authentication**: External JWT validation (expects JWT from an external auth service)
- **Use Case**: When you already have an existing authentication system
- **Benefits**: Lightweight and minimal resource usage

**Switch to Lite Version:**
```bash
git switch lite
```

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
- **Flexible Signature Verification**: Users authenticate using their crypto wallet or SSO credentials in an external trusted system than emmits a signed JWT.
- **Smart Contract Integration**: Validates users' lab reservations on-chain
- **JWT Token Generation**: Issues secure access tokens for lab sessions (to be consumed by Guacamole)

### ✅ Authentication Service (Spring Boot)
- **RESTful API**: Comprehensive authentication endpoints
- **Blockchain Integration**: Web3j for smart contract interaction
- **JWT Management**: Token validation and generation
- **Health Monitoring**: Built-in health checks and metrics

### ✅ Enhanced Gateway Features
- **CORS Support**: Cross-origin resource sharing for web applications
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Security Headers**: Comprehensive security header configuration
- **Real-time Monitoring**: Detailed logging and error tracking

## 🚀 Quick Deployment

### Using Setup Scripts (Recommended)

The setup scripts will automatically:
- ✅ Check Docker prerequisites
- ✅ Configure environment variables
- ✅ Set up database passwords (auto-generated or custom)
- ✅ Configure domain and ports (localhost vs production)
- ✅ Generate SSL certificates for localhost (if needed)
- ✅ Configure blockchain & institutional wallet settings
- ✅ Start all services automatically (including blockchain-services)

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
   ```

2. **Edit `.env` file** with your configuration:
   ```env
   # Blockchain Configuration
   CONTRACT_ADDRESS=0xYourSmartContractAddress
   RPC_URL=https://your-blockchain-rpc-endpoint.com
   WALLET_ADDRESS=0xYourWalletAddress
   WALLET_PRIVATE_KEY=0xYourPrivateKey
   INSTITUTIONAL_WALLET_ADDRESS=0xInstitutionalWallet
   INSTITUTIONAL_WALLET_PASSWORD=Sup3rSecret!
   WALLET_ENCRYPTION_SALT=ChangeThisSalt
   WALLET_PERSISTENCE_ENABLED=true
   WALLET_FILE_PATH=/app/data/wallets.json

   # Security Configuration
   ALLOWED_ORIGINS=https://your-frontend.com,https://marketplace.com
   MARKETPLACE_PUBLIC_KEY_URL=https://marketplace.com/.well-known/public-key.pem

   # Performance Tuning
   TOMCAT_MAX_THREADS=200
   LOG_LEVEL_AUTH=INFO
   ```

3. **Add SSL certificates** to `certs/` folder:
   ```
   certs/
   ├── fullchain.pem      # SSL certificate chain
   ├── privkey.pem        # SSL private key
   └── public_key.pem     # JWT public key (from marketplace/auth provider)
   ```

4. **Start the services:**
   ```bash
   docker-compose up -d --build
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
BASE_DOMAIN=https://yourdomain.com

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

**Setup:**
1. Copy templates: `cp .env.example .env && cp blockchain-services/.env.example blockchain-services/.env`
2. Edit both `.env` files with your values
3. See `blockchain-services/.env.example` for complete configuration options

### 🔑 Required Files

Place these files in the `certs/` directory:

```
certs/
├── fullchain.pem      # SSL certificate chain
├── privkey.pem        # SSL private key
└── public_key.pem     # JWT public key (from marketplace/auth provider)
```

## ?? Blockchain Wallet Persistence

The `blockchain-services` container mounts `./blockchain-data` into `/app/data` to keep the encrypted institutional wallet (`wallets.json`) between restarts. Create this folder before running Docker, lock down permissions, and add it to your backup plan. It is already ignored by git so you won't accidentally commit secrets.

## Blockchain-Services Submodule Management

The Full Version uses the blockchain-services as a Git submodule. Here's how to manage it:

### 📋 **When to Update the Submodule**

**Update Strategy - By Feature (Recommended):**
- ✅ After completing a new feature in blockchain-services
- ✅ When preparing for integration testing
- ✅ Before creating a release

### 🛠️ **Update Commands**

**Manual Update:**
```bash
# Update submodule to latest version
git submodule update --remote blockchain-services

# Commit the submodule update
git add blockchain-services
git commit -m "Update blockchain-services to latest version"
git push
```

**Automated Update (Recommended):**
```bash
# Windows
.\update-blockchain-services.bat "Integrate new blockchain features"

# Linux/macOS
./update-blockchain-services.sh "Integrate new blockchain features"
```

### 🔍 **Submodule Status**

Check submodule status:
```bash
# View current submodule status
git submodule status

# View available updates
git submodule summary

# Initialize submodule (if empty)
git submodule update --init --recursive
```

### 💡 **Development Workflow**

1. **Develop in blockchain-services repository** (separate directory)
2. **Test and commit changes** in blockchain-services
3. **Push blockchain-services changes** to GitHub
4. **Run update script** in Lab Gateway when ready to integrate
5. **Test full system** with updated blockchain-services
6. **Push Lab Gateway changes**

## 🛠️ Development

### Local Development Setup

1. **Start services in development mode:**
   ```bash
   SPRING_PROFILES_ACTIVE=dev docker-compose up -d
   ```

2. **Access services:**
   - Auth Service: http://localhost:8080/auth
   - Guacamole: https://localhost:8443/guacamole
   - MySQL: localhost:3306

### Debugging

Enable debug logging:
```env
LOG_LEVEL_AUTH=DEBUG
LOG_LEVEL_SECURITY=DEBUG
LOG_LEVEL_WEB=DEBUG
JPA_SHOW_SQL=true
```

### Hot Reload

The auth service supports hot reload in development:
```bash
# Rebuild only auth service
docker-compose build blockchain-services
docker-compose up -d blockchain-services
```

## 🪶 Migration from Lite Version

If you're upgrading from the Lite Version:

1. **Switch to full branch:**
   ```bash
   git switch full
   ```

2. **Run setup script:**
   ```bash
   ./setup.sh  # or setup.bat on Windows
   ```

3. **Configure blockchain + institutional wallet settings** in `.env`
4. **Update your frontend** to use wallet authentication
5. **Test the complete authentication flow**

## 📞 Support

- **Documentation**: Check this README and setup scripts
- **Logs**: Use `docker-compose logs [service]` for troubleshooting
- **Issues**: Report issues on the project repository
- **Configuration**: Review `.env.example` for all available options

---

*The Full Version provides a complete, production-ready blockchain authentication system for decentralized laboratory access.*
