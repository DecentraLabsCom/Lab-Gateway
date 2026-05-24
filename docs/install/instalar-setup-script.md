# Guía de instalación — Script de configuración (recomendado)

El script de configuración es la forma más rápida de poner en marcha Lab Gateway.
Gestiona los prerequisitos, ficheros de configuración, secretos y el arranque de
los contenedores en una única sesión interactiva.

## Prerequisitos

| Requisito | Versión mínima |
|---|---|
| Docker Engine (Linux) o Docker Desktop (Windows/macOS) | 20.10+ |
| Docker Compose | 2.0+ (incluido con Docker Desktop) |
| Git | cualquier versión reciente |
| 2 núcleos CPU, 4 GB RAM, 20 GB de disco libre | — |

Verifica que Docker funciona antes de ejecutar el script:

```bash
docker --version
docker compose version
```

## Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/DecentraLabsCom/lite-lab-gateway.git /srv/lab-gateway
cd /srv/lab-gateway
```

En Windows, clona en una ruta sin espacios, por ejemplo `C:\lab-gateway`.

## Paso 2 — Ejecutar el script de configuración

**Linux / macOS:**

```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**

```cmd
setup.bat
```

## Paso 3 — Responder las preguntas interactivas

El script te guiará automáticamente por los siguientes pasos:

1. **Comprueba los prerequisitos** — disponibilidad de Docker, Compose y Git.
2. **Inicializa los submódulos** — descarga `blockchain-services` si no se clonó de forma recursiva.
3. **Crea `.env` y `blockchain-services/.env`** — copia las plantillas incluidas en el repositorio.
4. **Pregunta el nombre de dominio** — se usa en TLS, CORS y la configuración del emisor OIDC.
5. **Genera contraseñas de base de datos** — valores aleatorios y seguros se escriben directamente en `.env`.
6. **Pregunta las credenciales de administrador de Guacamole** — usuario y contraseña para el panel de escritorio remoto.
7. **Pregunta sobre el Túnel Cloudflare** — opcional; úsalo si el servidor no tiene IP pública.
8. **Arranca el stack** — ejecuta `docker compose up -d` con todos los contenedores.

## Paso 4 — Verificar que el stack está en ejecución

```bash
docker compose ps
```

Todos los contenedores deben mostrar `Up`. Comprueba el endpoint de salud del gateway:

```bash
curl -k https://localhost/health
```

Respuesta esperada:

```json
{"status":"ok"}
```

## Paso 5 — Configurar la cartera institucional

1. Abre `https://tu-dominio/wallet-dashboard` en un navegador.
2. Introduce tu `ADMIN_ACCESS_TOKEN` (definido en `.env`) cuando se te solicite.
3. Haz clic en **Create wallet** (institución nueva) o **Import wallet** (clave existente).
4. La cartera cifrada se guarda en `blockchain-data/wallets.json` y se carga automáticamente en cada reinicio.

## Paso 6 — Añadir la configuración de blockchain

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

## Paso 7 — Configurar una conexión de laboratorio en Guacamole

Consulta [Conexiones Guacamole](../../configuring-lab-connections/guacamole-connections.md) para
la guía paso a paso sobre cómo añadir conexiones RDP/VNC a los ordenadores físicos del laboratorio.

## Solución de problemas

| Síntoma | Solución |
|---|---|
| Un contenedor termina inmediatamente | Ejecuta `docker compose logs <servicio>` para ver el error. |
| MySQL no arranca | Verifica que las contraseñas en `.env` no tengan el valor por defecto (`CHANGE_ME`). |
| `curl /health` devuelve error TLS | Añade `-k` para certificados autofirmados en desarrollo. En producción, verifica los certificados en `certs/`. |
| El dashboard de cartera pide el token repetidamente | Asegúrate de que `ADMIN_ACCESS_TOKEN` está definido en `.env` y de que el navegador no bloquea las cookies. |

## Próximos pasos

- [Configurar conexiones de laboratorio](../../configuring-lab-connections/guacamole-connections.md)
- [Instalación manual con Docker Compose](instalar-compose-manual.md)
- [Tutorial de operador de extremo a extremo](../tutorials/tutorial-primera-sesion-laboratorio.md)
