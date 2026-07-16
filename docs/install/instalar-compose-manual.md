# Guía de instalación — Docker Compose manual

Usa esta guía si quieres control total sobre cada paso de configuración sin ejecutar
el script interactivo de configuración.

## Prerequisitos

| Requisito | Versión mínima |
|---|---|
| Docker Engine (Linux) o Docker Desktop (Windows/macOS) | 20.10+ |
| Docker Compose | 2.0+ |
| Git | cualquier versión reciente |
| 2 núcleos CPU, 4 GB RAM, 20 GB de disco libre | — |

## Paso 1 — Clonar el repositorio

```bash
git clone --recurse-submodules https://github.com/DecentraLabsCom/Lab-Gateway.git /srv/lab-gateway
cd /srv/lab-gateway
```

Si ya clonaste sin `--recurse-submodules`, inicializa el submódulo manualmente:

```bash
git submodule update --init --recursive
```

## Paso 2 — Crear los ficheros de entorno

```bash
cp .env.example .env
cp blockchain-services/.env.example blockchain-services/.env
```

## Paso 3 — Configurar `.env` (Gateway)

Abre `.env` y establece como mínimo:

```env
# Tu dominio público
SERVER_NAME=lab.tu-institucion.edu

# Contraseñas fuertes — no dejes los valores por defecto
MYSQL_ROOT_PASSWORD=cambia_a_contraseña_segura
MYSQL_PASSWORD=cambia_a_contraseña_segura

# Administrador de Guacamole (no uses 'guacadmin' en producción)
GUAC_ADMIN_USER=admin
GUAC_ADMIN_PASS=cambia_a_contraseña_segura

# Protege las rutas de cartera/facturación frente a redes públicas
ADMIN_ACCESS_TOKEN=cambia_a_token_aleatorio

# Protege los endpoints del gestor de laboratorio y ops
LAB_MANAGER_TOKEN=cambia_a_token_aleatorio

# Orígenes permitidos para CORS (URL de tu Marketplace)
CORS_ALLOWED_ORIGINS=https://marketplace-decentralabs.vercel.app

# Obligatorio para la interpolación de Compose; usa el origen FMU público
FMU_JWT_AUDIENCE=https://lab.tu-institucion.edu/fmu
```

#### Modo del gateway

**Modo Full** (esta institución emite sus propios JWT):

```env
# Deja ISSUER vacío — es el valor por defecto
ISSUER=
```

**Modo Lite** (confía en los JWT de un gateway externo en modo Full):

```env
ISSUER=https://auth-gateway.otra-institucion.edu/auth
```

#### Dirección de escucha

```env
# Accesible desde el exterior (producción por defecto)
OPENRESTY_BIND_ADDRESS=0.0.0.0

# Solo local (desarrollo)
OPENRESTY_BIND_ADDRESS=127.0.0.1
```

#### Detrás de un NAT/router con reenvío de puertos

Si tu institución expone el puerto 8043 externamente pero Docker escucha en el 443:

```env
HTTPS_PORT=8043
OPENRESTY_BIND_HTTPS_PORT=443
```

## Paso 4 — Configurar `blockchain-services/.env`

```env
# Dirección del contrato inteligente (obtenida del despliegue de Smart-Contracts)
CONTRACT_ADDRESS=0xTuDireccionDeContrato

# Endpoints RPC (separados por comas para failover)
ETHEREUM_SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com,https://0xrpc.io/sep

# Funcionalidades de proveedor (obligatorio en modo Lab Gateway completo)
FEATURES_PROVIDERS_ENABLED=true
FEATURES_PROVIDERS_REGISTRATION_ENABLED=true

# Orígenes permitidos por el servicio de blockchain
ALLOWED_ORIGINS=https://lab.tu-institucion.edu,https://marketplace-decentralabs.vercel.app
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem
```

Deja `INSTITUTIONAL_WALLET_ADDRESS` e `INSTITUTIONAL_WALLET_PASSWORD` vacíos — se rellenan
automáticamente después de crear o importar una cartera a través de la consola web.

## Paso 5 — Establecer propietario de ficheros (solo Linux/macOS)

Obtén tu UID y GID:

```bash
id -u && id -g
```

Establécelos en `.env`:

```env
HOST_UID=1000
HOST_GID=1000
```

Crea y asigna propietario a los directorios de datos:

```bash
mkdir -p blockchain-data certs
chown -R 1000:1000 blockchain-data certs
```

## Paso 6 — Añadir certificados SSL

**Producción** — coloca aquí tus certificados de una CA o de Let's Encrypt:

```
certs/
├── fullchain.pem   # Cadena completa de certificados
└── privkey.pem     # Clave privada
```

**Let's Encrypt (automático)** — establece en `.env` y arranca con el perfil `certbot`:

```env
CERTBOT_DOMAINS=lab.tu-institucion.edu
CERTBOT_EMAIL=admin@tu-institucion.edu
CERTBOT_STAGING=0
```

```bash
docker compose --profile certbot up -d
```

**Desarrollo** — los certificados autofirmados se generan automáticamente al primer arranque
si `certs/` está vacío.

## Paso 7 — Arrancar el stack

```bash
docker compose up -d --build
```

Observa los logs mientras los contenedores se inicializan:

```bash
docker compose logs -f
```

## Paso 8 — Verificar el estado de salud

```bash
# Capa de enrutamiento del gateway
curl -k https://localhost/health

# Servicios de blockchain
curl -k https://localhost/auth/.well-known/openid-configuration
```

Ambos deben devolver JSON sin errores. La respuesta pública de salud está deliberadamente reducida; los operadores de Lab Manager pueden usar `/health/details` con el `LAB_MANAGER_TOKEN` configurado para obtener el diagnóstico detallado.

## Paso 9 — Crear la cartera institucional

1. Abre `https://lab.tu-institucion.edu/wallet-dashboard`.
2. Introduce el `ADMIN_ACCESS_TOKEN` definido en `.env`.
3. Haz clic en **Create wallet** o **Import wallet**.
4. Reinicia `blockchain-services` para cargar la configuración de la cartera:

```bash
docker compose restart blockchain-services
```

## Paso 10 — Configurar conexiones de laboratorio en Guacamole

Consulta [Conexiones Guacamole](../../configuring-lab-connections/guacamole-connections.md).

## Comandos útiles

```bash
# Detener todo
docker compose down

# Reiniciar un único servicio
docker compose restart openresty

# Seguir los logs de un servicio
docker compose logs -f blockchain-services

# Forzar la reconstrucción tras cambios en el código
docker compose up -d --build blockchain-services
```

## Próximos pasos

- [Instalación en NixOS](instalar-nixos.md)
- [Tutorial de operador de extremo a extremo](../tutorials/tutorial-primera-sesion-laboratorio.md)
