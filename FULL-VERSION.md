# 🚀 DecentraLabs Gateway - Full Version

## 🎯 Overview

The Full Version of DecentraLabs Gateway provides a complete blockchain-based authentication system for laboratory access. It includes all components needed for a decentralized lab access solution.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Wallet   │    │  OpenResty      │    │  Auth Service   │
│   (MetaMask)    ├────┤  (Nginx + Lua)  ├────┤  (Spring Boot)  │
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
- **Wallet Signature Verification**: Users authenticate using their crypto wallet
- **Smart Contract Integration**: Validates lab reservations on-chain
- **JWT Token Generation**: Issues secure access tokens for lab sessions
- **Multi-Provider Support**: Supports both own and external labs

### ✅ Authentication Service (Spring Boot)
- **RESTful API**: Comprehensive authentication endpoints
- **Blockchain Integration**: Web3j for smart contract interaction
- **JWT Management**: Token generation and validation
- **Redis Caching**: Performance optimization for frequent queries
- **Health Monitoring**: Built-in health checks and metrics

### ✅ Enhanced Gateway Features
- **CORS Support**: Cross-origin resource sharing for web applications
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Security Headers**: Comprehensive security header configuration
- **Real-time Monitoring**: Detailed logging and error tracking

### ✅ Advanced Infrastructure
- **Redis Cache**: Fast session management and data caching
- **Improved Networking**: Service discovery and load balancing
- **Health Checks**: Comprehensive health monitoring for all services
- **Resource Management**: Optimized resource allocation and limits

## 🚀 Quick Deployment

### Using Setup Scripts (Recommended)

**Windows:**
```cmd
setup.bat
```

**Linux/macOS:**
```bash
./setup.sh
```

### Manual Deployment

1. **Ensure you're on the full branch:**
   ```bash
   git checkout full
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Deploy services:**
   ```bash
   docker-compose up -d --build
   ```

## ⚙️ Configuration

### 🔧 Environment Variables

The full version requires additional configuration in `.env`:

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

### 🔑 Required Files

Place these files in the `certs/` directory:

```
certs/
├── fullchain.pem      # SSL certificate chain
├── privkey.pem        # SSL private key
└── public_key.pem     # JWT public key (from marketplace/auth provider)
```

## 🔐 Authentication Flow

### 1. Wallet Challenge
```
POST /auth/auth
{
  "wallet_address": "0x742d35Cc6E7C0532f3E8bc8F3aF1c567aE7aF2"
}

Response:
{
  "message": "0x742d35Cc6E7C0532f3E8bc8F3aF1c567aE7aF2:1695478400",
  "timestamp": 1695478400
}
```

### 2. Signature Verification
```
POST /auth/auth2
{
  "wallet_address": "0x742d35Cc6E7C0532f3E8bc8F3aF1c567aE7aF2",
  "signature": "0x1234567890abcdef...",
  "message": "0x742d35Cc6E7C0532f3E8bc8F3aF1c567aE7aF2:1695478400"
}

Response:
{
  "jwt": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "redirect_url": "https://yourdomain.com/guacamole/?jwt=..."
}
```

### 3. Lab Access
The JWT token contains lab access permissions based on blockchain reservations:

```json
{
  "iss": "https://yourdomain.com/auth",
  "aud": "https://yourdomain.com/guacamole",
  "sub": "0x742d35Cc6E7C0532f3E8bc8F3aF1c567aE7aF2",
  "labs": [
    {
      "provider": "university-chemistry",
      "lab_id": "reactor-control-01",
      "reservation_id": "res_894736",
      "valid_until": 1695482000
    }
  ],
  "exp": 1695482000,
  "iat": 1695478400
}
```

## 📊 API Endpoints

### Authentication Endpoints
- `POST /auth/auth` - Request wallet challenge
- `POST /auth/auth2` - Verify signature and get JWT
- `GET /auth/jwks` - Get public keys (JWKS format)
- `GET /auth/health` - Health check endpoint

### Administrative Endpoints
- `GET /auth/metrics` - Service metrics
- `GET /auth/status` - Detailed service status
- `POST /auth/refresh` - Refresh JWT token

### Marketplace Integration
- `POST /auth/marketplace-auth` - Marketplace JWT validation
- `POST /auth/marketplace-auth2` - Extended marketplace validation

## 🔍 Monitoring & Logging

### Service Health Checks
```bash
# Check all services
docker-compose ps

# Check specific service health
curl https://yourdomain.com/auth/health

# View detailed metrics
curl https://yourdomain.com/auth/metrics
```

### Log Access
```bash
# Auth service logs
docker-compose logs -f auth-service

# All services logs
docker-compose logs -f

# Real-time monitoring
docker-compose logs -f --tail=100
```

### Performance Monitoring

The auth service provides detailed metrics:
- Request rate and response times
- Blockchain query performance
- JWT token generation stats
- Cache hit/miss ratios
- Error rates and types

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

## 🔒 Security Considerations

### Production Checklist

- [ ] Change all default passwords
- [ ] Configure proper SSL certificates
- [ ] Set secure blockchain private keys
- [ ] Configure appropriate CORS origins
- [ ] Enable rate limiting
- [ ] Set up log monitoring and alerting
- [ ] Configure backup strategies
- [ ] Implement secret management
- [ ] Regular security updates

### Network Security

The full version includes enhanced security:
- Service-to-service communication isolation
- Rate limiting and DDoS protection
- Comprehensive security headers
- JWT token expiration and rotation
- Input validation and sanitization

## 🚨 Troubleshooting

### Common Issues

**Auth service fails to start:**
```bash
# Check logs
docker-compose logs auth-service

# Common causes:
# - Missing certificates in certs/
# - Invalid blockchain configuration
# - Database connection issues
```

**Blockchain connection failures:**
```bash
# Check RPC endpoint
curl -X POST -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  $RPC_URL

# Check contract address and ABI
```

**JWT validation errors:**
```bash
# Verify public key matches auth service
# Check token expiration and claims
# Verify issuer and audience configuration
```

### Performance Issues

**High response times:**
- Check Redis cache configuration
- Monitor blockchain RPC latency
- Review database query performance
- Check resource limits in docker-compose.yml

**Memory usage:**
- Monitor Java heap size in auth service
- Check Redis memory usage
- Review MySQL buffer pool configuration

## 📈 Scaling & Production

### Horizontal Scaling

The full version supports scaling:

```yaml
# Scale auth service
auth-service:
  deploy:
    replicas: 3
  # Add load balancer configuration
```

### Production Deployment

For production environments:

1. **Use external databases** (managed MySQL, Redis)
2. **Implement load balancing** (HAProxy, AWS ALB)
3. **Set up monitoring** (Prometheus, Grafana)
4. **Configure log aggregation** (ELK stack)
5. **Implement backup strategies**
6. **Set up CI/CD pipelines**

## 📞 Support

- **Documentation**: Check the `/dev` directory for detailed technical docs
- **Logs**: Use `docker-compose logs [service]` for troubleshooting
- **Issues**: Report issues on the project repository
- **Configuration**: Review `.env.example` for all available options

---

*The Full Version provides a complete, production-ready blockchain authentication system for decentralized laboratory access.*