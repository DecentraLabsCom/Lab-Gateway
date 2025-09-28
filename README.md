# Lab Gateway 🧪

Lab Gateway is a laboratory virtualization solution that enables remote access to lab environments. It's available in two versions with different levels of features and authentication.

## 📋 Available Versions

### Lite Version (Branch `lite`)
Basic version with essential features:
- ✅ RDP/VNC/SSH access to lab computers
- ✅ Intuitive web interface
- ✅ Auth through input JWTs
- ✅ Reverse proxy with OpenResty
- ✅ MySQL database for Guacamole configuration
- ✅ Complete containerization with Docker
- ✅ Simple configuration

**Ideal for**: Development environments, personal testing, quick deployments.

### Full Version (Branch `full`)
Complete version with advanced authentication:
- ✅ All Lite version features
- ✅ **Blockchain-based authentication**
- ✅ **JWT generation system**
- ✅ **Advanced user management**
- ✅ **REST APIs for integration**
- ✅ **Administration dashboard**
- ✅ **Complete logging and auditing**

**Ideal for**: Production environments, enterprise deployments, maximum security.

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

- **Lite Version**: See [LITE-VERSION.md](./LITE-VERSION.md)
- **Full Version**: See [FULL-VERSION.md](./FULL-VERSION.md)

## 🔄 Detailed Comparison

| Feature | Lite | Full |
|---|---|---|
| **RDP Access** | ✅ | ✅ |
| **Web Interface** | ✅ | ✅ |
| **Docker Compose** | ✅ | ✅ |
| **MySQL + Guacamole** | ✅ | ✅ |
| **OpenResty Proxy** | ✅ | ✅ |
| **Auth Through JWT** | ✅ | ✅ |
| **Blockchain Authentication** | ❌ | ✅ |
| **Spring Boot Auth Service** | ❌ | ✅ |
| **JWT Generation** | ❌ | ✅ |
| **REST APIs** | ❌ | ✅ |
| **Admin Dashboard** | ❌ | ✅ |
| **Redis Session Store** | ❌ | ✅ |
| **Complete Auditing** | ❌ | ✅ |

## �️ Technology Stack

### Core Components (Both Versions)
- **OpenResty** - Reverse proxy and load balancer
- **Apache Guacamole** - RDP/VNC gateway
- **MySQL** - Primary database
- **Docker & Docker Compose** - Containerization

### Full Version Additions
- **Spring Boot** - Authentication service
- **Redis** - Session store and cache
- **JWT** - Authentication tokens
- **Blockchain Integration** - Decentralized authentication

## � Project Structure

```
lab-gateway/
├── 📁 openresty/          # Reverse proxy configuration
├── 📁 guacamole/          # RDP/VNC client
├── 📁 mysql/              # DB scripts and schemas
├── 📁 web/                # Web frontend
├── 📁 certs/              # SSL certificates
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

- **Issues**: [GitHub Issues](https://github.com/DecentraLabsCom/lite-lab-gateway/issues)
- **Documentation**: Check LITE-VERSION.md or FULL-VERSION.md according to your version

---

> **Note**: This README serves as a navigation hub. For specific installation and configuration instructions, check the documentation for each version.