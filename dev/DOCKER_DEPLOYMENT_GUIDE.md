# Guía de Contenerización - Auth Service con Docker

## 🐳 Integración en Stack Docker Existente

### **📋 Contexto**
- Stack existente con OpenResty, Java, Tomcat, MySQL y Guacamole
- Auth-service como WAR desplegado en Apache Tomcat
- Configuración optimizada para producción

## 🏗️ Arquitectura - Contenedor Dedicado

```
┌─────────────────────────────────────────┐
│               Docker Compose            │
├─────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────────┐   │
│  │auth-service │  │   Guacamole     │   │
│  │(Spring Boot)│  │   (Tomcat)      │   │
│  │   :8082     │  │     :8080       │   │
│  └─────────────┘  └─────────────────┘   │
│           │               │             │
│  ┌─────────────────────────────────┐    │
│  │          MySQL                  │    │
│  │  guacamole_db    auth_db        │    │
│  │           :3306                 │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## 🚀 Implementación

## 🏭 Build Multi-Stage (Recomendado)

**Ventajas:**
- ✅ No requiere WAR local ni Maven instalado
- ✅ Build reproducible en cualquier máquina
- ✅ Imagen optimizada (sin dependencias de build)
- ✅ Perfecto para CI/CD

### **Estructura de Proyecto:**
```
auth-service/
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── application.properties
│   └── logback-spring.xml
├── keys/
│   ├── private_key.pem
│   ├── public_key.pem
│   └── certificate.pem
├── sql/
│   └── init-auth-db.sql
├── target/
│   └── auth-service.war
└── scripts/
    ├── entrypoint.sh
    └── health-check.sh
```

### **Dockerfile Multi-Stage**

```dockerfile
# Build Stage - Compila el código fuente
FROM maven:3.8.6-openjdk-11 AS builder

WORKDIR /build

# Copy POM first for better Docker layer caching
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Copy source code and build
COPY src ./src
RUN mvn clean package -DskipTests -B

# Verify WAR was created
RUN test -f target/auth-service.war

#########################################
# Runtime Stage - Imagen final optimizada
#########################################
FROM openjdk:11-jre-slim

# Metadata
LABEL maintainer="DecentraLabs <tech@decentralabs.com>"
LABEL version="1.0.0"
LABEL description="Auth Service - JWT Authentication for Marketplace"

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    netcat \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Application directory
WORKDIR /app

# Copy WAR from builder stage
COPY --from=builder /build/target/auth-service.war ./auth-service.war

# Copy configuration and scripts
COPY config/application.properties ./config/
COPY keys/ ./keys/
COPY scripts/entrypoint.sh ./entrypoint.sh
COPY scripts/health-check.sh ./health-check.sh

# Make scripts executable and set ownership
RUN chmod +x ./entrypoint.sh ./health-check.sh && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ./health-check.sh

# Entry point
ENTRYPOINT ["./entrypoint.sh"]
```

### **2. Docker Compose (Integración con Stack Existente)**

```yaml
# docker-compose.yml
version: '3.8'

services:
  auth-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: auth-service
    restart: unless-stopped
    
    # Environment variables
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      - JAVA_OPTS=-Xmx1024m -Xms512m
      - TZ=Europe/Madrid
    
    # Port mapping (8080 ocupado por Guacamole/Tomcat)
    ports:
      - "8082:8080"  # Puerto 8082 para evitar conflicto con Guacamole
    
    # Volumes (persistent data)
    volumes:
      - ./config/application.properties:/app/config/application.properties:ro
      - ./keys:/app/keys:ro
      - ./logs:/app/logs
    
    # Network
    networks:
      - app-network
    
    # Dependencies
    depends_on:
      mysql:
        condition: service_healthy
    
    # Health check override
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/auth/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
      # Nota: El health check interno usa 8080 (puerto del contenedor)

  # Tu base de datos existente (si no está ya definida)
  mysql:
    image: mysql:8.0
    container_name: mysql-db
    restart: unless-stopped
    
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      # Base de datos separada para auth-service
      MYSQL_DATABASE: auth_db
      MYSQL_USER: auth_user
      MYSQL_PASSWORD: ${AUTH_DB_PASSWORD}
    
    volumes:
      - mysql-data:/var/lib/mysql
      - ./sql/init-auth-db.sql:/docker-entrypoint-initdb.d/01-init-auth-db.sql:ro
      # Mantener tu script de inicialización de Guacamole si existe:
      # - ./sql/init-guacamole.sql:/docker-entrypoint-initdb.d/00-init-guacamole.sql:ro
    
    ports:
      - "3306:3306"
    
    networks:
      - app-network
    
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 10s
      retries: 3
      start_period: 30s

  # Guacamole existente (mantener configuración actual)
  guacamole:
    image: tomcat:9-jdk11
    container_name: guacamole-tomcat
    restart: unless-stopped
    
    volumes:
      - ./guacamole.war:/usr/local/tomcat/webapps/guacamole.war:ro
      # Mantener tu configuración existente de Guacamole
    
    ports:
      - "8080:8080"  # Puerto ocupado por Guacamole
    
    networks:
      - app-network
    
    depends_on:
      mysql:
        condition: service_healthy

# Networks
networks:
  app-network:
    driver: bridge

# Volumes
volumes:
  mysql-data:
    driver: local
```

### **3. Scripts de Soporte**

#### **entrypoint.sh**
```bash
#!/bin/bash
# scripts/entrypoint.sh

set -e

echo "🚀 Starting Auth Service..."
echo "Environment: ${SPRING_PROFILES_ACTIVE:-default}"
echo "Java Options: ${JAVA_OPTS:-default}"

# Wait for dependencies
echo "⏳ Waiting for dependencies..."
if [ -n "$MYSQL_HOST" ]; then
    echo "Waiting for MySQL at $MYSQL_HOST:${MYSQL_PORT:-3306}..."
    while ! nc -z $MYSQL_HOST ${MYSQL_PORT:-3306}; do
        sleep 1
    done
    echo "✅ MySQL is ready!"
fi

# Check configuration
if [ ! -f "./config/application.properties" ]; then
    echo "❌ Configuration file not found!"
    exit 1
fi

# Check keys
if [ ! -f "./keys/private_key.pem" ]; then
    echo "❌ Private key not found!"
    exit 1
fi

echo "✅ Configuration and keys verified"

# Start application
echo "🔄 Starting Auth Service application..."
exec java $JAVA_OPTS -jar auth-service.war \
    --spring.config.location=file:./config/application.properties \
    --spring.profiles.active=${SPRING_PROFILES_ACTIVE:-docker}
```

#### **health-check.sh**
```bash
#!/bin/bash
# scripts/health-check.sh

# Internal health check for Docker
curl -f http://localhost:8080/auth/health >/dev/null 2>&1

if [ $? -eq 0 ]; then
    exit 0
else
    echo "Health check failed"
    exit 1
fi
```

### **4. Configuración Docker-Específica**

#### **config/application.properties**
```properties
# Docker-specific configuration
server.servlet.context-path=/auth
server.port=8080

# Server configuration
base.domain=https://sarlab.dia.uned.es

# Endpoint paths
endpoint.auth=/auth
endpoint.auth2=/auth2
endpoint.jwks=/jwks
endpoint.message=/message
endpoint.marketplace-auth=/marketplace-auth
endpoint.marketplace-auth2=/marketplace-auth2
endpoint.guacamole=/guacamole
endpoint.health=/health

# JWT configuration (paths relative to container)
private.key.path=./keys/private_key.pem
public.key.path=./keys/public_key.pem
public.certificate.path=./keys/certificate.pem

# Database (base de datos separada de Guacamole)
spring.datasource.url=jdbc:mysql://mysql:3306/auth_db
spring.datasource.username=auth_user
spring.datasource.password=${AUTH_DB_PASSWORD}
spring.jpa.hibernate.ddl-auto=update
spring.jpa.database-platform=org.hibernate.dialect.MySQL8Dialect

# Blockchain configuration
contract.address=${CONTRACT_ADDRESS}
rpc.url=${RPC_URL}
wallet.address=${WALLET_ADDRESS}
wallet.private.key=${WALLET_PRIVATE_KEY}

# Security
allowed-origins=${ALLOWED_ORIGINS:http://localhost:3000,https://marketplace-decentralabs.vercel.app}

# Marketplace JWT
marketplace.public-key-url=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem

# Logging
logging.level.root=INFO
logging.level.decentralabs.auth=DEBUG
logging.file.name=./logs/auth-service.log
logging.pattern.file=%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n
```

#### **.env (Variables de Entorno)**
```env
# .env file
MYSQL_ROOT_PASSWORD=secure_root_password

# Base de datos separada para auth-service
AUTH_DB_PASSWORD=secure_auth_password

# Variables específicas de Guacamole (mantener las existentes)
# GUACAMOLE_DB_PASSWORD=tu_password_guacamole

# Application variables
CONTRACT_ADDRESS=0xYourContractAddress
RPC_URL=https://your-blockchain-rpc.com
WALLET_ADDRESS=0xYourWalletAddress
WALLET_PRIVATE_KEY=0xYourPrivateKey

ALLOWED_ORIGINS=http://localhost:3000,https://marketplace-decentralabs.vercel.app

# Java options
JAVA_OPTS=-Xmx1024m -Xms512m -XX:+UseG1GC
```

### **5. Nginx Reverse Proxy (Opcional pero Recomendado)**

```yaml
# Agregar a docker-compose.yml
  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    restart: unless-stopped
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    
    networks:
      - app-network
    
    depends_on:
      - auth-service
      - existing-app
```

#### **nginx.conf**
```nginx
events {
    worker_connections 1024;
}

http {
    upstream auth-service {
        server auth-service:8080;
    }
    
    upstream existing-app {
        server existing-app:8080;
    }
    
    server {
        listen 80;
        server_name sarlab.dia.uned.es;
        
        # Auth service (puerto 8082)
        location /auth/ {
            proxy_pass http://auth-service;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Guacamole (puerto 8080 - mantener configuración existente)
        location /guacamole/ {
            proxy_pass http://guacamole:8080/guacamole/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Health checks
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
```

## 🚀 Comandos de Despliegue

### **Construcción y Despliegue:**

```bash
# 1. Build y deploy en un solo comando
# El Dockerfile multi-stage compila automáticamente el código
docker-compose build auth-service
docker-compose up -d

# 2. Verificar servicios
docker-compose ps
docker-compose logs -f auth-service

# 3. Probar health endpoint (puerto 8082)
curl http://localhost:8082/auth/health
```

**Nota:** No necesitas compilar el WAR localmente ni tener Maven instalado. Docker se encarga de todo el proceso de build.

### **Comandos de Gestión:**

```bash
# Monitoreo
docker-compose logs -f auth-service              # Ver logs en tiempo real
docker-compose ps                                # Estado de contenedores
docker stats auth-service                        # Estadísticas de recursos

# Mantenimiento
docker-compose build auth-service                # Rebuild imagen
docker-compose up -d auth-service               # Actualizar servicio
docker-compose restart auth-service             # Reiniciar servicio

# Debugging
docker-compose exec auth-service bash           # Acceder al contenedor
docker-compose exec auth-service curl http://localhost:8080/auth/health  # Health check interno
```

## 🔧 Integración con Stack Existente

### **Modificar tu docker-compose.yml existente:**

```yaml
# Agregar al services: de tu docker-compose.yml existente
  auth-service:
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    container_name: auth-service
    restart: unless-stopped
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      - JAVA_OPTS=-Xmx1024m -Xms512m
      - AUTH_DB_PASSWORD=${AUTH_DB_PASSWORD}
    ports:
      - "8082:8080"  # Puerto 8082 para evitar conflicto con Guacamole
    volumes:
      - ./auth-service/config:/app/config:ro
      - ./auth-service/keys:/app/keys:ro
      - ./auth-service/logs:/app/logs
    networks:
      - your-existing-network  # Usar tu red existente
    depends_on:
      - your-existing-mysql    # Tu MySQL existente
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/auth/health"]
      interval: 30s
      timeout: 10s
      retries: 3

# Agregar el script de inicialización de BD si tu MySQL no lo tiene:
# volumes:
#   - ./auth-service/sql/init-auth-db.sql:/docker-entrypoint-initdb.d/01-init-auth-db.sql:ro
```

## 🔗 Integración Específica con Guacamole

### **Configuración Recomendada:**

**1. Puertos:**
- Guacamole: `8080` (mantener actual)
- Auth-service: `8082` (nuevo)

**2. Base de Datos:**
- `guacamole_db`: Base de datos existente de Guacamole
- `auth_db`: Nueva base de datos para auth-service

**3. Endpoints de Integración:**
Si Guacamole necesita usar el auth-service:
```bash
# Endpoint de autenticación desde Guacamole
curl -X POST http://localhost:8082/auth/guacamole \
  -H "Content-Type: application/json" \
  -d '{"token": "jwt_token_here"}'
```

### **Variables de Entorno Específicas:**

```env
# .env - Agregar a tu configuración existente
AUTH_DB_PASSWORD=secure_auth_password
GUACAMOLE_DB_PASSWORD=tu_password_actual_guacamole

# URLs para integración
AUTH_SERVICE_URL=http://auth-service:8080
GUACAMOLE_URL=http://guacamole:8080
```

### **Docker Compose Integrado (Ejemplo Completo):**

```yaml
# docker-compose-integrated.yml
version: '3.8'

services:
  # Tu configuración actual de Guacamole
  guacamole:
    image: guacamole/guacamole:latest
    container_name: guacamole
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      GUACD_HOSTNAME: guacd
      MYSQL_HOSTNAME: mysql
      MYSQL_DATABASE: guacamole_db
      MYSQL_USER: guacamole_user
      MYSQL_PASSWORD: ${GUACAMOLE_DB_PASSWORD}
    networks:
      - app-network
    depends_on:
      - guacd
      - mysql

  guacd:
    image: guacamole/guacd:latest
    container_name: guacd
    restart: unless-stopped
    networks:
      - app-network

  # Nuevo auth-service
  auth-service:
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    container_name: auth-service
    restart: unless-stopped
    ports:
      - "8082:8080"
    environment:
      - SPRING_PROFILES_ACTIVE=docker
      - AUTH_DB_PASSWORD=${AUTH_DB_PASSWORD}
    volumes:
      - ./auth-service/config:/app/config:ro
      - ./auth-service/keys:/app/keys:ro
      - ./auth-service/logs:/app/logs
    networks:
      - app-network
    depends_on:
      mysql:
        condition: service_healthy

  # MySQL compartido con ambas bases de datos
  mysql:
    image: mysql:8.0
    container_name: mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql-data:/var/lib/mysql
      # Scripts de inicialización en orden
      - ./sql/00-init-guacamole.sql:/docker-entrypoint-initdb.d/00-init-guacamole.sql:ro
      - ./auth-service/sql/init-auth-db.sql:/docker-entrypoint-initdb.d/01-init-auth-db.sql:ro
    ports:
      - "3306:3306"
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 10s
      retries: 3

networks:
  app-network:
    driver: bridge

volumes:
  mysql-data:
```

### **Pasos de Migración desde tu Stack Actual:**

**1. Preparación:**
```bash
# Backup de tu configuración actual
docker-compose exec mysql mysqldump -u root -p guacamole_db > backup_guacamole.sql

# Crear directorios para auth-service
mkdir -p auth-service/{config,keys,sql,scripts}
```

**2. Agregar auth-service:**
```bash
# Agregar servicio al docker-compose existente
# (el build multi-stage compila automáticamente)
docker-compose build auth-service
docker-compose up -d auth-service
```

**3. Inicializar base de datos:**
```bash
# Ejecutar script de inicialización
docker-compose exec mysql mysql -u root -p < auth-service/sql/init-auth-db.sql
```

**4. Verificar integración:**
```bash
# Verificar ambos servicios
curl http://localhost:8080/guacamole/api/  # Guacamole
curl http://localhost:8082/auth/health     # Auth-service
```