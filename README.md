# 🚀 DecentraLabs Gateway - Full Version

## 🎯 Overview

The Full Version of DecentraLabs Gateway provides a complete blockchain-based authentication system for laboratory access. It includes all components needed for a decentralized lab access solution with advanced features and monitoring.

## 🔀 Version Information

You are currently on the **Full Version** branch. This project offers two versions:

### 🚀 **Full Version** (Current Branch)
- **Purpose**: Complete blockchain-based authentication system
- **Components**: Auth Service (Spring Boot) + Redis + OpenResty + Guacamole + MySQL
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
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Wallet   │    │  OpenResty      │    │  Auth Service   │
│   or JWT        ├────┤  (Nginx + Lua)  ├────┤  (Spring Boot)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                │                        │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Guacamole     │    │     Redis       │
                       │  (Lab Access)   │    │   (Caching)     │
                       └─────────────────┘    └─────────────────┘
                                │                        │
                                │                        │
                       ┌─────────────────┐    ┌─────────────────┐
                       │     MySQL       │    │   Blockchain    │
                       │   (Database)    │    │   (Smart        │
                       └─────────────────┘    │   Contracts)    │
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
- **Redis Caching**: Performance optimization for frequent queries
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
- ✅ Configure blockchain settings
- ✅ Start all services automatically (including auth-service)

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

   # Redis Configuration
   REDIS_PASSWORD=secure_redis_password

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

The full version requires additional configuration in `.env`:

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

# Blockchain Configuration
CONTRACT_ADDRESS=0xYourSmartContractAddress
RPC_URL=https://your-blockchain-rpc-endpoint.com
WALLET_ADDRESS=0xYourWalletAddress
WALLET_PRIVATE_KEY=0xYourPrivateKey

# Redis Configuration
REDIS_PASSWORD=secure_redis_password

# Security Configuration
ALLOWED_ORIGINS=https://your-frontend.com,https://marketplace.com
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace.com/.well-known/public-key.pem

# Performance Tuning
TOMCAT_MAX_THREADS=200
LOG_LEVEL_AUTH=INFO
```

### 🔑 Required Files

Place these files in the `certs/` directory:

```
certs/
├── fullchain.pem      # SSL certificate chain
├── privkey.pem        # SSL private key
└── public_key.pem     # JWT public key (from marketplace/auth provider)
```

## Auth-Service Submodule Management

The Full Version uses the auth-service as a Git submodule. Here's how to manage it:

### 📋 **When to Update the Submodule**

**Update Strategy - By Feature (Recommended):**
- ✅ After completing a new feature in auth-service
- ✅ When preparing for integration testing
- ✅ Before creating a release

### 🛠️ **Update Commands**

**Manual Update:**
```bash
# Update submodule to latest version
git submodule update --remote auth-service

# Commit the submodule update
git add auth-service
git commit -m "Update auth-service to latest version"
git push
```

**Automated Update (Recommended):**
```bash
# Windows
.\update-auth-service.bat "Integrate new blockchain features"

# Linux/macOS
./update-auth-service.sh "Integrate new blockchain features"
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

1. **Develop in auth-service repository** (separate directory)
2. **Test and commit changes** in auth-service
3. **Push auth-service changes** to GitHub
4. **Run update script** in Lab Gateway when ready to integrate
5. **Test full system** with updated auth-service
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
   - Redis: localhost:6379

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
docker-compose build auth-service
docker-compose up -d auth-service
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

3. **Configure blockchain settings** in `.env`
4. **Update your frontend** to use wallet authentication
5. **Test the complete authentication flow**

## 📞 Support

- **Documentation**: Check this README and setup scripts
- **Logs**: Use `docker-compose logs [service]` for troubleshooting
- **Issues**: Report issues on the project repository
- **Configuration**: Review `.env.example` for all available options

---

*The Full Version provides a complete, production-ready blockchain authentication system for decentralized laboratory access.*