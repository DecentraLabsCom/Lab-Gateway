# Guía de instalación — Script de configuración (recomendado)

El script de configuración es la forma más rápida de poner en marcha Lab Gateway.
Gestiona los prerequisitos, ficheros de configuración, secretos y el arranque de
los contenedores en una única sesión interactiva.

## Prerequisitos

Instala Docker/Compose, Git y Python 3. Python 3 se utiliza para migrar la
configuración del entorno SAML antes de iniciar los contenedores.

| Requisito | Versión mínima |
|---|---|
| Docker Engine (Linux) o Docker Desktop (Windows/macOS) | 20.10+ |
| Plugin de Docker Compose | 2.14.0+ (`docker compose`; no se admite el legacy `docker-compose`) |
| Git | cualquier versión reciente |
| 2 núcleos CPU, 4 GB RAM, 20 GB de disco libre | — |

Verifica que Docker funciona antes de ejecutar el script:

```bash
docker --version
docker compose version
```

El script requiere el plugin de Docker Compose 2.14.0 o posterior. El gateway
actual se ha probado con el plugin v2.35.1. Ejecuta primero el script de
instalación para que genere los ficheros locales usados por los secretos de
Compose.

El script crea el directorio ignorado `secrets/` a partir de las credenciales
de `.env`, lo protege con permisos de directorio `0750` y asigna los ficheros
a `HOST_UID:HOST_GID`. Los ficheros usan modo `0644` porque los secretos
respaldados por ficheros de Compose son montajes directos y varios servicios
ejecutan con un usuario no root propio de su imagen, que puede no coincidir
con `HOST_UID`; el directorio sigue impidiendo el acceso de usuarios locales no
autorizados. Mantén ese directorio en el host mientras el gateway esté
instalado; no debe incluirse en Git ni borrarse de forma independiente del
fichero de entorno.

## Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/DecentraLabsCom/Lab-Gateway.git Lab-Gateway
cd Lab-Gateway
```

En Windows, clona en una ruta sin espacios, por ejemplo `C:\lab-gateway`.

## Paso 2 - Opcional: anadir certificados TLS de produccion

Si ya tienes un certificado para el dominio del gateway, copialo dentro de
`certs/` antes de ejecutar el setup:

```bash
mkdir -p certs
cp /ruta/fullchain.pem certs/fullchain.pem
cp /ruta/privkey.pem certs/privkey.pem
chmod 700 certs
chmod 600 certs/privkey.pem
chmod 644 certs/fullchain.pem
```

El script detecta `certs/fullchain.pem` y `certs/privkey.pem`. Si omites este
paso, OpenResty genera certificados autofirmados para desarrollo/pruebas locales.

Si anades o sustituyes estos archivos cuando el stack ya esta en ejecucion,
reinicia OpenResty:

```bash
docker compose restart openresty
```

## Paso 3 - Ejecutar el script de configuracion

**Linux / macOS:**

```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**

```cmd
setup.bat
```

## Paso 4 - Responder las preguntas interactivas

El script te guía automáticamente por los siguientes pasos:

1. **Comprueba los prerequisitos e inicializa los submódulos**, incluido el
   repositorio embebido `blockchain-services`.
2. **Crea y protege `.env` y `blockchain-services/.env`**, y genera secretos
   distintos para base de datos, operador, redención, observación y Ops Worker.
3. **Configura el borde público**, el dominio, los puertos directos o detrás de
   NAT/router, el alcance administrativo, Guacamole y Lab Manager.
4. **Selecciona el modo Full o Lite**: `ISSUER` vacío crea un Gateway Full;
   un `ISSUER` externo selecciona Lite. Lite exige un trust bundle coincidente
   emitido por el plano de control Full remoto.
5. **Configura capacidades opcionales**: FMU y, únicamente en Full, AAS
   integrado, externo o deshabilitado.
6. **Ofrece Cloudflare Tunnel** y arranca los servicios de Compose elegidos.

El script es interactivo deliberadamente. Para un cambio repetible y no
interactivo, usa la [guía manual de Compose](instalar-compose-manual.md) y la
[referencia de configuración](../reference/configuration.md).

## Paso 5 - Verificar que el stack esta en ejecucion

```bash
docker compose ps
```

Los contenedores principales deben mostrar `Up`; perfiles opcionales como
`fmu-runner`, `aas`, `certbot` o Cloudflare pueden no estar activos. Comprueba
el endpoint de salud del gateway:

```bash
curl -k https://localhost/health
```

Los servicios gestionados por Compose, incluido `guacamole`, quedan con
política de reinicio automático. Si se habilitó el perfil `fmu-local-dev`, su
runner también se reiniciará tras reiniciar Docker o el equipo. En Linux,
verifica además que Docker se inicie con el sistema:

```bash
sudo systemctl enable --now docker
```

En Windows, activa **Start Docker Desktop when you sign in** en la
configuración de Docker Desktop.

La respuesta pública es agregada deliberadamente y es apta para balanceadores.
Un borde sano devuelve `status: "UP"`; usa `/gateway/health` para la salud
agregada del plano de acceso local. Tras abrir una sesión de Lab Manager, usa
`/health/details` o `/gateway/health/details` para el diagnóstico de
dependencias.

```json
{"status":"UP","service":"lab-gateway","mode":"full","public":true}
```

## Paso 6 - Configurar la cartera institucional

1. Abre `https://tu-dominio/wallet-dashboard` en un navegador.
2. Introduce tu `ADMIN_ACCESS_TOKEN` (definido en `.env`) cuando se te solicite.
3. Haz clic en **Create wallet** (institución nueva) o **Import wallet** (clave existente).
4. La cartera cifrada se guarda en `blockchain-data/wallets.json` y se carga automáticamente en cada reinicio.

## Paso 7 - Anadir la configuracion de blockchain

Edita `blockchain-services/.env` y establece:

```env
CONTRACT_ADDRESS=0xTuDireccionDeContratoDeplegado
ETHEREUM_SEPOLIA_RPC_URL=https://tu-nodo-rpc
INSTITUTIONAL_WALLET_ADDRESS=  # dejar vacío — se rellena automáticamente tras crear la cartera
INSTITUTIONAL_WALLET_PASSWORD= # dejar vacío — se rellena automáticamente tras crear la cartera
ALLOWED_ORIGINS=https://tu-dominio.com
```

Reinicia el contenedor de blockchain-services para aplicar los cambios:

```bash
docker compose restart blockchain-services
```

## Paso 8 - Configurar una conexion de laboratorio en Guacamole

Consulta [Conexiones Guacamole](../configuring-lab-connections/guacamole-connections.md) para
la guía paso a paso sobre cómo añadir conexiones RDP/VNC a los ordenadores físicos del laboratorio.

## Solución de problemas

| Síntoma | Solución |
|---|---|
| Un contenedor termina inmediatamente | Ejecuta `docker compose logs <servicio>` para ver el error. |
| MySQL no arranca | Verifica que las contraseñas en `.env` no tengan el valor por defecto (`CHANGE_ME`). |
| `curl /health` devuelve error TLS | Añade `-k` para certificados autofirmados en desarrollo. En producción, verifica los certificados en `certs/`. |
| El dashboard de cartera pide el token repetidamente | Asegúrate de que `ADMIN_ACCESS_TOKEN` está definido en `.env` y de que el navegador no bloquea las cookies. |

## Próximos pasos

- [Configurar conexiones de laboratorio](../configuring-lab-connections/guacamole-connections.md)
- [Instalación manual con Docker Compose](instalar-compose-manual.md)
- [Tutorial de operador de extremo a extremo](../tutorials/tutorial-primera-sesion-laboratorio.md)
- [Operación y salud](../reference/operations-and-health.md)
