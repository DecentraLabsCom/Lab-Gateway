# Guía de instalación — Docker Compose manual

Usa esta guía si quieres control total sobre cada paso de configuración sin ejecutar
el script interactivo de configuración.

Antes de editar los ficheros de entorno, elige la topología del plano de
control en [Arquitecturas de despliegue](../deployment-architectures.md). La
referencia completa de variables y perfiles opcionales está en
[Configuration reference](../reference/configuration.md).

## Prerequisitos

| Requisito | Versión mínima |
|---|---|
| Docker Engine (Linux) o Docker Desktop (Windows/macOS) | 20.10+ |
| Plugin de Docker Compose | 2.14.0+ (`docker compose`; no se admite el legacy `docker-compose`) |
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
GUACAMOLE_MYSQL_USER=guacamole_app
GUACAMOLE_MYSQL_PASSWORD=cambia_a_contraseña_segura
BLOCKCHAIN_MYSQL_USER=blockchain_app
BLOCKCHAIN_MYSQL_PASSWORD=cambia_a_contraseña_segura
OPS_BACKEND_MYSQL_USER=ops_backend
OPS_BACKEND_MYSQL_PASSWORD=cambia_a_contraseña_segura
OPS_GUACAMOLE_MYSQL_USER=ops_guac
OPS_GUACAMOLE_MYSQL_PASSWORD=cambia_a_contraseña_segura
OPS_SECRETS_KEY=<clave-fernet-estable>
WINRM_MANAGEMENT_CIDRS=10.7.74.0/24

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

En un gateway Full, configura tambien las credenciales usadas para el canje de
codigos de acceso opacos y la observacion de sesiones FMU. Los valores JSON
deben ser objetos JSON validos y la clave debe coincidir exactamente con el
`SERVER_NAME` normalizado. No uses una cadena con formato `host:token`:

```env
AUTH_ACCESS_CODE_REDEEMER_TOKEN=<token-aleatorio-de-canje>
ACCESS_CODE_ENCRYPTION_KEY=<clave-base64url-para-32-bytes>
ACCESS_CODE_REDEEMER_CREDENTIALS_JSON={"lab.tu-institucion.edu":"<token-aleatorio-de-canje>"}
SESSION_OBSERVER_GATEWAY_ID=lab.tu-institucion.edu
SESSION_OBSERVER_SIGNING_SECRET=<secreto-base64url-para-32-bytes>
SESSION_OBSERVER_CREDENTIALS_JSON={"lab.tu-institucion.edu":"<secreto-base64url-para-32-bytes>"}
```

Genera de forma independiente la clave de cifrado y el secreto del observador.
Ambos deben decodificar exactamente a 32 bytes:

```bash
openssl rand -base64 32 | tr '+/' '-_' | tr -d '='
```

Ejecuta el comando dos veces y usa valores distintos. El token de canje puede
ser cualquier secreto aleatorio de alta entropia; por ejemplo:

```bash
openssl rand -hex 32
```

Los gateways Lite deben usar las credenciales y el trust bundle emitidos por el
gateway Full remoto en lugar de inventar mapas locales de modo Full.

## Paso 3a — Generar los ficheros de secretos de Compose

El fichero Compose utiliza secretos respaldados por ficheros del host porque
varios servicios ejecutan con el sistema de ficheros raíz en solo lectura.
Genéralos después de configurar `.env` y `HOST_UID`/`HOST_GID`, antes de
ejecutar `docker compose config` o `docker compose up`.

Linux, macOS o WSL:

```bash
python3 scripts/validate-gateway-env.py --env .env
bash scripts/sync-compose-secrets.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Validate-GatewayEnv.ps1 -EnvPath .\.env
powershell -ExecutionPolicy Bypass -File .\scripts\Sync-ComposeSecrets.ps1
```

Valida el modelo de Compose renderizado antes de iniciar los servicios:

```bash
docker compose config --quiet
docker compose config --services
docker compose config --profiles
```

El comando crea el directorio ignorado `secrets/` con permisos de directorio
`0750` y ficheros `0644`. El modo de los ficheros debe permitir que los
servicios no root lean los secretos montados por Compose; el directorio sigue
restringiendo el acceso local. Ejecútalo de nuevo cada vez que cambie un
secreto en `.env`. No incluyas ni borres este directorio mientras el
despliegue esté en uso.

En Linux, no ejecutes los comandos anteriores hasta completar el Paso 5:
`HOST_UID`, `HOST_GID` y los directorios persistentes deben estar preparados.
El validador debe terminar sin errores antes de continuar con Compose.

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
gateway_uid="$(id -u)"
gateway_gid="$(id -g)"

mkdir -p blockchain-data certs fmu-access-state lab-content fmu-data \
  fmu-proxy-runtime/binaries/linux64 \
  fmu-proxy-runtime/binaries/win64 \
  fmu-proxy-runtime/binaries/darwin64 \
  ops-data/guac-revocation-spool

sudo chown -R "${gateway_uid}:${gateway_gid}" \
  blockchain-data certs fmu-access-state lab-content
chmod 700 fmu-access-state
chmod 755 lab-content fmu-data fmu-proxy-runtime \
  fmu-proxy-runtime/binaries fmu-proxy-runtime/binaries/linux64 \
  fmu-proxy-runtime/binaries/win64 fmu-proxy-runtime/binaries/darwin64
chmod 700 ops-data ops-data/guac-revocation-spool
```

En particular, `fmu-access-state` debe ser escribible por el UID de OpenResty
porque almacena los mapeos FMU cifrados y persistentes. Si ejecutas el stack
mediante `sudo`, conserva el `HOST_UID` y `HOST_GID` de la cuenta de despliegue;
no los sustituyas silenciosamente por los de root.

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

Habilita servicios opcionales solo cuando estén configurados y sean necesarios.
Por ejemplo, la fachada FMU de producción es exclusiva para Lab Station y usa
su propio perfil:

```env
FMU_RUNNER_ENABLED=true
FMU_BACKEND_MODE=station
FMU_LOCAL_DEV_MODE=false
FMU_LOCAL_REALTIME_ENABLED=false
FMU_STATION_BASE_URL=https://station.internal.example
FMU_STATION_INTERNAL_TOKEN=<station-internal-token>
```

```bash
docker compose --profile fmu-runner up -d --build
```

Para ejecución FMU local exclusiva de desarrollo usa `fmu-local-dev`; nunca
arranques los dos perfiles FMU a la vez. Activa explícitamente el realtime
local:

```env
FMU_RUNNER_ENABLED=true
FMU_BACKEND_MODE=local
FMU_LOCAL_DEV_MODE=true
FMU_LOCAL_REALTIME_ENABLED=true
```

```bash
docker compose --profile fmu-local-dev up -d --build openresty fmu-runner-local
```

La ejecución local necesita `secrets/session_observer_signing_secret`, generado
a partir de `SESSION_OBSERVER_SIGNING_SECRET`, para canjear tickets FMU y
registrar sesiones aceptadas. No necesita credenciales de Lab Station ni de
administrador.

Para la ejecución local, coloca cada FMU publicado en uno de los layouts
soportados y haz coincidir `accessKey`/`fmuFileName` con el recurso configurado:

```text
fmu-data/<accessKey>.fmu
fmu-data/<accessKey>/model.fmu
```

Consulta [FMU data layout](../../fmu-data/README.md) para el almacenamiento por
proveedor y [soporte FMI/FMU](../fmi-fmu-support.md) para publicación y validación.

`FMU_BACKEND_MODE` controla dónde se ejecuta el FMU; el modo Full/Lite determina
independientemente el origen de JWKS. Los scripts de setup guardan
automáticamente `FMU_LOCAL_REALTIME_ENABLED=true` cuando se selecciona el
backend local. Mantén `false` para el perfil de producción respaldado por Lab
Station. Consulta la
[referencia de configuración](../reference/configuration.md).

## Paso 8 — Verificar el estado de salud

```bash
# Capa de enrutamiento del gateway
curl -k https://localhost/health

# Servicios de blockchain
curl -k https://localhost/auth/.well-known/openid-configuration
```

Si FMU esta habilitado, verifica tambien el runner seleccionado y el montaje
del estado persistente:

```bash
docker compose ps openresty fmu-runner fmu-runner-local
docker compose exec -T openresty id
stat -c '%u:%g %a %n' fmu-access-state
docker compose exec -T openresty sh -c '
  set -eu
  probe=/var/lib/openresty/fmu-access/.write-test-$$
  printf test > "$probe"
  rm -f "$probe"
  echo "OpenResty puede escribir el estado FMU"
'
```

El UID/GID de OpenResty debe coincidir con el propietario de
`fmu-access-state`. Un health check correcto por si solo no prueba esta ruta de
escritura.

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

Consulta [Conexiones Guacamole](../configuring-lab-connections/guacamole-connections.md).

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
- [Operación y salud](../reference/operations-and-health.md)
