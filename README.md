# 🪶 DecentraLabs Gateway - Lite Version

## 🎯 Overview

The Lite Version of DecentraLabs Gateway provides a lightweight, JWT-validated laboratory access system. It's designed for environments where you already have an existing authentication system and just need secure lab access.

## 🔀 Version Information

You are currently on the **Lite Version** branch. This project offers two versions:

### 🪶 **Lite Version** (Current Branch)
- **Purpose**: JWT-validated gateway for lab access
- **Components**: OpenResty + Guacamole + MySQL
- **Authentication**: External JWT validation (expects JWT from external auth service)
- **Use Case**: When you already have an existing authentication system
- **Benefits**: Lightweight and minimal resource usage

### 🚀 **Full Version** 
- **Purpose**: Complete blockchain-based authentication system
- **Components**: Auth Service (Spring Boot) + Redis + OpenResty + Guacamole + MySQL
- **Authentication**: Blockchain wallet signature verification or signed JWT verification + blockchain smart contract checks
- **Features**: Wallet-based auth, smart contract integration
- **Use Case**: Complete decentralized lab access solution

**Switch to Full Version:**
```bash
git switch full
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  External Auth  │    │    OpenResty    │    │   Guacamole     │
│    Service      ├────┤  (Nginx + Lua)  ├────┤  (Lab Access)   │
│   (Issues JWT)  │    │ (JWT validation)│    └─────────────────┘
└─────────────────┘    └─────────────────┘            │
                                                      │
                                              ┌─────────────────┐
                                              │     MySQL       │
                                              │   (Database)    │
                                              └─────────────────┘
```

## 🌟 Features

### ✅ Lightweight Design
- **Minimal Components**: Only essential services (OpenResty, Guacamole, MySQL)
- **Low Resource Usage**: Optimized for small deployments
- **Quick Deployment**: Fast startup and easy configuration
- **Simple Maintenance**: Fewer components to manage

### ✅ JWT Authentication
- **External JWT Validation**: Validates tokens from your existing auth service
- **Flexible Integration**: Works with any JWT-issuing authentication system
- **Secure Access Control**: Comprehensive token validation
- **Session Management**: Automatic session handling and cleanup

### ✅ Essential Security
- **SSL/TLS Termination**: Secure HTTPS connections
- **Security Headers**: Basic security header configuration
- **Access Logging**: Request logging and monitoring
- **Input Validation**: Basic request validation

## 🚀 Quick Deployment

### Using Setup Scripts (Recommended)

The setup scripts will automatically:
- ✅ Check Docker prerequisites
- ✅ Configure environment variables
- ✅ Set up database passwords (auto-generated or custom)
- ✅ Configure domain and ports (localhost vs production)
- ✅ Generate SSL certificates for localhost (if needed)
- ✅ Start all services automatically

**Windows:**
```cmd
setup.bat
```

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

That's it! The script will guide you through the setup and start the services automatically.

### Manual Deployment

If you prefer manual configuration:

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file** with your configuration:
   ```env
   SERVER_NAME=yourdomain.com          # Your domain
   HTTPS_PORT=443                      # 443 for production, 8443 for dev
   HTTP_PORT=80                        # 80 for production, 8080 for dev
   MYSQL_ROOT_PASSWORD=secure_password # MySQL root password
   MYSQL_PASSWORD=guac_db_password     # Guacamole database password
   ```

3. **Add SSL certificates** to `certs/` folder:
   ```
   certs/
   ├── fullchain.pem     # SSL certificate
   ├── privkey.pem       # SSL private key
   └── public_key.pem    # JWT public key
   ```

4. **Start the services:**
   ```bash
   docker-compose up -d
   ```

## ⚙️ Configuration

### 🔧 Environment Variables

The lite version requires minimal configuration in `.env`:

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

# Guacamole Configuration
GUAC_ADMIN_USER=guacadmin
GUAC_ADMIN_PASS=guacadmin
ISSUER=YourAuthServiceName
```

### 🔑 Required Files

Place these files in the `certs/` directory:

```
certs/
├── fullchain.pem      # SSL certificate chain
├── privkey.pem        # SSL private key
└── public_key.pem     # JWT public key (from your auth service)
```

## 🔐 JWT Integration

### External Authentication Service Requirements

Your authentication service must issue JWT tokens with these claims:

```json
{
  "iss": "https://your-auth-service.com",     # Issuer (your auth service)
  "aud": "https://yourdomain.com/guacamole",  # Audience (this gateway)
  "sub": "username",                          # Subject (user identifier)
  "jti": "unique-token-id",                   # JWT ID (prevents replay)
  "exp": 1693478400,                          # Expiration timestamp
  "iat": 1693474800                           # Issued at timestamp
}
```

### Access URLs

Users access the lab gateway using JWT tokens from your auth service:

```
https://yourdomain.com/guacamole/?jwt=YOUR_JWT_TOKEN
```

### Public Key Configuration

The `public_key.pem` file must contain the public key that corresponds to the private key used by your authentication service to sign JWT tokens.

## 📊 Service Management

### Health Checks
```bash
# Check all services
docker-compose ps

# Check specific service logs
docker-compose logs -f openresty
docker-compose logs -f guacamole
docker-compose logs -f mysql
```

### Service Control
```bash
# Restart services
docker-compose restart [service_name]

# Stop all services
docker-compose down

# Update services
docker-compose pull && docker-compose up -d
```

## 🔍 Monitoring & Logging

### Access Logs
OpenResty provides detailed access logging:
```bash
docker-compose logs -f openresty
```

### Database Monitoring
```bash
# Access MySQL
docker exec -it [mysql_container] mysql -u root -p

# Monitor database connections
docker exec -it [mysql_container] mysqladmin processlist -u root -p
```

## 🛠️ Development

### Local Development Setup

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Access services:**
   - Guacamole: https://localhost:8443/guacamole
   - MySQL: localhost:3306

### Testing JWT Integration

Test your JWT tokens:
```bash
# Decode JWT payload (for debugging)
echo "YOUR_JWT_TOKEN" | cut -d. -f2 | base64 -d | jq .

# Test gateway access
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://yourdomain.com/guacamole/
```

## 📈 Migration to Full Version

If you later need blockchain authentication features:

1. **Switch to full branch:**
   ```bash
   git switch full
   ```

2. **Deploy full version:**
   ```bash
   ./setup.sh  # or setup.bat on Windows
   ```

3. **Configure blockchain settings:**
   - Set up smart contract addresses
   - Configure blockchain RPC endpoints
   - Set up wallet authentication

## 📞 Support

- **Documentation**: Check this README and setup scripts
- **Logs**: Use `docker-compose logs [service]` for troubleshooting
- **Issues**: Report issues on the project repository
- **Configuration**: Review `.env.example` for all available options

---

*The Lite Version provides a simple, efficient solution for JWT-based laboratory access when you already have an authentication system in place.*