# 🚀 DecentraLabs Gateway

A secure, containerized laboratory access gateway with optional blockchain-based authentication.

## 🔀 Available Versions

This project offers two versions to meet different requirements:

### 🪶 **Lite Version** (`lite` branch)
- **Purpose**: Basic JWT-validated gateway for lab access
- **Components**: OpenResty + Guacamole + MySQL
- **Authentication**: External JWT validation (expects JWT from external auth service)
- **Use Case**: When you have an existing authentication system
- **Benefits**: Lightweight, minimal resource usage, simple deployment

### 🚀 **Full Version** (`full` branch) - **Current Branch**
- **Purpose**: Complete blockchain-based authentication system
- **Components**: Auth Service (Spring Boot) + Redis + OpenResty + Guacamole + MySQL
- **Authentication**: Blockchain wallet signature verification + JWT generation
- **Features**: 
  - Wallet-based authentication
  - Smart contract integration
  - Real-time dashboard
  - Comprehensive monitoring
  - Multi-provider lab support
- **Use Case**: Complete decentralized lab access solution

## 🔄 Switching Between Versions

```bash
# Switch to lite version (minimal setup)
git checkout lite

# Switch to full version (with blockchain auth service)
git checkout full
```

## ⚡ Quick Start

### Automated Setup (Recommended)

The setup scripts will automatically:
- ✅ Check Docker prerequisites
- ✅ Configure environment variables
- ✅ Set up database passwords (auto-generated or custom)
- ✅ Configure domain and ports (localhost vs production)
- ✅ Generate SSL certificates for localhost (if needed)
- ✅ Start all services automatically

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```cmd
setup.bat
```

That's it! The script will guide you through the setup and start the services automatically.

#### 🎯 Setup Script Features

The automated setup scripts provide:

- **🔍 Prerequisites check**: Verifies Docker and Docker Compose installation
- **🔐 Smart password management**: Auto-generates secure passwords or lets you set custom ones
- **🌐 Intelligent domain configuration**: Automatically configures for localhost (dev) or production
- **� Flexible port selection**: Choose between standard (443/80) or custom ports
- **�📜 SSL certificate handling**: Generates self-signed certs for localhost, guides for production
- **🚀 One-command deployment**: Starts all services automatically after configuration
- **⚠️ Safe overwrite protection**: Asks before overwriting existing `.env` files

### Manual Setup (Advanced Users)

If you prefer manual configuration:

1. **Copy environment template:**
   ```bash
   # For full version (current branch)
   cp .env.full .env
   
   # Or for lite version
   # cp .env.lite .env
   ```

2. **Edit `.env` file** with your configuration:
   ```env
   # Basic Configuration
   SERVER_NAME=yourdomain.com          # Your domain
   HTTPS_PORT=443                      # 443 for production, 8443 for dev
   HTTP_PORT=80                        # 80 for production, 8080 for dev
   
   # Database Configuration
   MYSQL_ROOT_PASSWORD=secure_password # MySQL root password
   MYSQL_PASSWORD=guac_db_password     # Guacamole database password
   
   # Full Version: Blockchain Authentication (only for full version)
   CONTRACT_ADDRESS=0xYourContractAddress
   RPC_URL=https://your-blockchain-rpc.com
   WALLET_ADDRESS=0xYourWalletAddress
   WALLET_PRIVATE_KEY=0xYourPrivateKey
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

## 🔐 JWT Authentication Setup

This lite gateway validates JWT tokens from an Auth2 Service before allowing access to Guacamole.

### Required Configuration

1. **Environment Variables** (in `.env` file):
   ```env
   SERVER_NAME=yourdomain.com                    # Must match JWT 'aud' claim
   ISSUER=https://auth-service.com/auth     # Must match JWT 'iss' claim
   ```

2. **Public Key** (in `certs/public_key.pem`):
   - Must be the public key from the Auth Service
   - Used to verify JWT token signatures

### JWT Token Requirements

The Auth Service must issue JWT tokens with these claims:

```json
{
  "iss": "https://auth-service.com/auth",    # Issuer (the auth service)
  "aud": "https://yourdomain.com/guacamole", # Audience (this gateway)
  "sub": "username",                         # Subject (user identifier)
  "jti": "unique-token-id",                  # JWT ID (prevents replay)
  "exp": 1693478400,                         # Expiration timestamp
  "iat": 1693474800                          # Issued at timestamp
}
```

### Access URLs

- **With JWT**: `https://yourdomain.com/guacamole/?jwt=YOUR_TOKEN`
- **Direct login**: `https://yourdomain.com/guacamole/` (uses Guacamole's built-in auth)

## 🔐 SSL Certificates

The setup scripts handle SSL certificates automatically:

### For Development (localhost)
- **Automatic**: The setup script generates self-signed certificates
- **Manual**: Place your own certificates in the `certs/` folder

### For Production
You need valid SSL certificates. The setup script will guide you, but you need to obtain them from:

- **Let's Encrypt** (free):
  ```bash
  certbot certonly --standalone -d yourdomain.com
  cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem certs/
  cp /etc/letsencrypt/live/yourdomain.com/privkey.pem certs/
  ```

- **Cloud Providers**: AWS ACM, Cloudflare, etc.
- **Commercial CA**: DigiCert, GlobalSign, etc.

### JWT Public Key

The `public_key.pem` file contains the **public key from the Authentication Service** that issues JWT tokens. This key is used by the gateway to verify that incoming JWT tokens are valid and haven't been tampered with.

#### 🔑 Key Requirements

**Important**: The `public_key.pem` must be the public key that corresponds to the private key used by the Auth Service to sign JWT tokens.

#### 🔄 JWT Authentication Flow

1. **Auth Service** (e.g., `https://sarlab.dia.uned.es/auth`) signs JWT tokens with its **private key**
2. **Gateway** receives JWT tokens from users and verifies them using the **public key**
3. If verification succeeds, the gateway allows access to Guacamole
4. If verification fails, access is denied

#### 📋 How to Obtain the Public Key

**From your Auth Service provider:**
```bash
# If the auth service provides a JWKS endpoint
curl https://auth-service.com/.well-known/jwks.json

# If the auth service provides the public key directly
curl https://auth-service.com/public-key.pem > certs/public_key.pem
```

**For development/testing only or if you want to run your own auth service** (generates a new key pair):
```bash
# Generate private key (this is kept in the auth service)
openssl genrsa -out jwt_private.pem 2048

# Extract public key (use this in the gateway)
openssl rsa -in jwt_private.pem -pubout -out certs/public_key.pem
```

#### ⚠️ Security Notes

- **Never generate your own keys for production** - use the public key from your Auth Service
- The private key should **only exist on your Auth Service**, never on the gateway
- If you change keys on your Auth Service, update `public_key.pem` on the gateway
- The gateway validates JWT claims: `iss` (issuer), `aud` (audience), `exp` (expiration), and `jti` (JWT ID)

## 🌐 Configuration Examples

The setup scripts use intelligent defaults, but you can customize ports in `.env` after setup:

### Local Development
```env
SERVER_NAME=localhost
ISSUER=https://localhost/auth
HTTPS_PORT=8443  # Development port (no admin needed)
HTTP_PORT=8080   # Development port (no admin needed)
```
Access: https://localhost:8443

### Production
```env
SERVER_NAME=lab.university.edu
ISSUER=https://lab.university.edu/auth
HTTPS_PORT=443   # Standard HTTPS port
HTTP_PORT=80     # Standard HTTP port
```
Access: https://lab.university.edu

## 📂 Project Structure

```
├── docker-compose.yml           # Main orchestration
├── .env.example                 # Environment template
├── setup.sh / setup.bat         # Setup scripts
├── certs/                       # SSL certificates and keys (not in git)
│   ├── fullchain.pem            # SSL certificate chain
│   ├── privkey.pem              # SSL private key
│   └── public_key.pem           # JWT verification public key (from Auth Service)
├── openresty/                   # NGINX + Lua proxy
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── lab_access.conf
│   └── lua/                     # Authentication scripts
├── guacamole/                   # Guacamole container
│   ├── Dockerfile
│   ├── guacamole.properties
│   ├── extensions/
│   └── lib/
├── mysql/                       # Database initialization
│   ├── 001-create-schema.sql
│   ├── 002-create-admin-user.sql
│   └── 003-rdp-example.sql
└── web/                         # Homepage
    ├── index.html
    └── assets/
```

## 🔑 Default Credentials

- **Username**: `guacadmin`
- **Password**: `guacadmin`

⚠️ **Change these in production!** Access the Guacamole admin panel to create new users and disable the default account.

## 🎯 Usage

### Access Methods

1. **Direct Access**: https://yourdomain.com/guacamole/
2. **JWT Authentication**: https://yourdomain.com/guacamole/?jwt=YOUR_TOKEN
3. **Homepage**: https://yourdomain.com/

### Adding Connections

1. Login to Guacamole admin panel
2. Go to Settings → Connections
3. Add RDP/VNC/SSH connections as needed

## 🛠️ Development

### View Logs
```bash
docker-compose logs -f openresty
docker-compose logs -f guacamole
```

### Restart Services
```bash
docker-compose restart openresty
docker-compose restart guacamole
```

### Database Access
```bash
# Get the database password from .env file
docker exec -it dockerlabgateway-mysql-1 mysql -u guacamole_user -p guacamole_db
# Enter the password from MYSQL_PASSWORD in your .env file
```

## 🔒 Security Considerations

- **Setup script helps with security**: Auto-generates strong passwords
- Change default admin password after first login
- Use valid SSL certificates in production (not self-signed)
- Keep JWT private keys secure
- Regular security updates
- Network firewall configuration
- Monitor access logs

## 📚 Documentation

- [OpenResty Documentation](https://openresty.org/)
- [Apache Guacamole Manual](https://guacamole.apache.org/doc/gug/)
- [Docker Compose Reference](https://docs.docker.com/compose/)

## 🆘 Troubleshooting

### Common Issues

**Port conflicts:**
- Change `HTTPS_PORT` and `HTTP_PORT` in `.env`
- Check what's using ports: `netstat -tulpn | grep :443`

**Certificate errors:**
- Verify certificate files exist in `certs/`
- Check certificate validity: `openssl x509 -in certs/fullchain.pem -text -noout`
- Ensure `SERVER_NAME` matches certificate CN/SAN

**Database connection issues:**
- Check MySQL container logs: `docker-compose logs mysql`
- Verify database credentials match those in `.env` file

**Guacamole not accessible:**
- Check if all containers are running: `docker-compose ps`
- Verify OpenResty configuration: `docker-compose logs openresty`

**JWT Authentication issues:**
- Verify `public_key.pem` matches the Auth Service's private key
- Check JWT token format: `echo "JWT_TOKEN" | base64 -d` (decode payload)
- Ensure `iss` claim matches `ISSUER` in `.env`
- Ensure `aud` claim matches `https://SERVER_NAME/guacamole`
- Check OpenResty logs for detailed JWT validation errors: `docker-compose logs openresty`
- Verify token hasn't expired (`exp` claim)
- Ensure `jti` (JWT ID) is unique for each token

For more help, open an issue on GitHub.
