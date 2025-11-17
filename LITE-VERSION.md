# Lite Version Guide

> **Note**: You are viewing documentation for the **Lite Version** (branch `lite`). For the full blockchain-based version with wallet authentication and institutional treasury management, see the [main README](README.md) on the `main` branch.

## 🎯 Overview

The Lite Version of DecentraLabs Gateway provides a lightweight, JWT-validated laboratory access system. It's designed for environments where you already have an existing authentication system and just need secure lab access without blockchain integration.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  External Auth  │    │   OpenResty     │    │   Guacamole     │
│    Service      ├────┤  (Nginx + Lua)  ├────┤  (Lab Access)   │
│   (Issues JWT)  │    │ (JWT Validation)│    └─────────────────┘
└─────────────────┘    └─────────────────┘             │
                                                       │
                                              ┌─────────────────┐
                                              │     MySQL       │
                                              │   (Database)    │
                                              └─────────────────┘
```

## 🌟 Features

### ✅ Lightweight Design

* **Minimal Components**: Only essential services (OpenResty, Guacamole, MySQL)
* **Low Resource Usage**: Optimized for small deployments
* **Quick Deployment**: Fast startup and easy configuration
* **Simple Maintenance**: Fewer components to manage

### ✅ JWT Authentication

* **External JWT Validation**: Validates tokens from your existing auth service
* **Flexible Integration**: Works with any JWT-issuing authentication system
* **Secure Access Control**: Comprehensive token validation
* **Session Management**: Automatic session handling and cleanup

### ✅ Essential Security

* **SSL/TLS Termination**: Secure HTTPS connections
* **Security Headers**: Basic security header configuration
* **Access Logging**: Request logging and monitoring
* **Input Validation**: Basic request validation

## 🚀 Quick Deployment

### Using Setup Scripts (Recommended)

**Windows:**

```cmd
setup.bat
```

**Linux/macOS:**

```bash
chmod +x setup.sh
./setup.sh
```

### Manual Deployment

1.  **Ensure you're on the lite branch:**

    ```bash
    git checkout lite
    ```
2.  **Configure environment:**

    ```bash
    cp .env.example .env
    # Edit .env with your configuration
    ```
3.  **Deploy services:**

    ```bash
    docker compose up -d
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
```

The issuer advertised in JWT validation comes from `SERVER_NAME` and `HTTPS_PORT`. Only override it if absolutely necessary by setting the `ISSUER` environment variable when launching OpenResty (for example `docker run -e ISSUER=https://custom/auth ...`).

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
docker compose ps

# Check specific service logs
docker compose logs -f openresty
docker compose logs -f guacamole
docker compose logs -f mysql
```

### Service Control

```bash
# Restart services
docker compose restart [service_name]

# Stop all services
docker compose down

# Update services
docker compose pull && docker compose up -d
```

## 🔍 Monitoring & Logging

### Access Logs

OpenResty provides detailed access logging:

```bash
docker compose logs -f openresty
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

1.  **Start services:**

    ```bash
    docker compose up -d
    ```
2. **Access services:**
   * Guacamole: https://localhost:8443/guacamole
   * MySQL: localhost:3306

### Testing JWT Integration

Test your JWT tokens:

```bash
# Decode JWT payload (for debugging)
echo "YOUR_JWT_TOKEN" | cut -d. -f2 | base64 -d | jq .

# Test gateway access
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://yourdomain.com/guacamole/
```

## 🔒 Security Considerations

### Production Checklist

* [ ] Change all default passwords
* [ ] Configure proper SSL certificates
* [ ] Set correct JWT public key from your auth service
* [ ] Configure appropriate issuer and audience
* [ ] Set up log monitoring
* [ ] Configure backup strategies
* [ ] Regular security updates

### Minimal Attack Surface

The lite version minimizes security risks by:

* Fewer components to secure
* No blockchain integration complexity
* Simplified network topology
* Standard JWT validation

## 🚨 Troubleshooting

### Common Issues

**JWT validation fails:**

```bash
# Check public key matches your auth service
# Verify token expiration and claims
# Check issuer and audience configuration
```

**Guacamole connection issues:**

```bash
# Check container logs
docker compose logs guacamole

# Verify database connection
docker compose logs mysql
```

### Performance Optimization

For better performance:

* Use external MySQL database in production
* Configure proper resource limits
* Enable log rotation
* Monitor memory usage

## 🚀 Upgrade to Full Version

If you later need blockchain authentication features and institutional treasury management:

1.  **Switch to main branch:**

    ```bash
    git checkout main
    ```
2.  **Deploy full version:**

    ```bash
    ./setup.sh  # or setup.bat on Windows
    ```
3. **Configure blockchain settings:**
   * Set up smart contract addresses in `blockchain-services/.env`
   * Configure blockchain RPC endpoints
   * Set up wallet authentication
   * Create or import institutional wallet

See the [main README](README.md) for complete documentation on the full version.

## 📞 Support

* **Documentation**: Check this README and the [main README](README.md) for full version features
* **Logs**: Use `docker compose logs [service]` for troubleshooting
* **Issues**: Report issues on the [project repository](https://github.com/DecentraLabsCom/lite-lab-gateway/issues)
* **Configuration**: Review `.env.example` for all available options

***

_The Lite Version provides a simple, efficient solution for JWT-based laboratory access when you already have an authentication system in place._
