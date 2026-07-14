# Guía de instalación — NixOS (host gestionado con Compose)

Usa esta guía para desplegar Lab Gateway en una máquina NixOS dedicada utilizando el
`flake.nix` incluido. Este modo gestiona de forma declarativa tanto el sistema operativo
como todos los servicios del gateway a través de systemd.

> **Alcance**: esta guía cubre `nixosConfigurations.gateway` — la única ruta de despliegue
> NixOS soportada en producción. Las rutas NixOS componetizadas y los bundles de imágenes
> deterministas fueron evaluados y eliminados del alcance activo; este enfoque gestionado
> con Compose es la línea base de producción.

## Prerequisitos

- Una máquina o VM con **NixOS 23.05+** y flakes habilitados.
- Acceso a Internet desde el host de destino (para descargar entradas del flake e imágenes de contenedores).
- `git` disponible en el host de destino.

Habilitar flakes (añadir a `/etc/nixos/configuration.nix` si no está ya configurado):

```nix
nix.settings.experimental-features = [ "nix-command" "flakes" ];
```

## Paso 1 — Colocar el repositorio en el host de destino

```bash
sudo mkdir -p /srv
sudo git clone --recurse-submodules https://github.com/DecentraLabsCom/Lab-Gateway.git /srv/lab-gateway
cd /srv/lab-gateway
```

## Paso 2 — Crear los ficheros de entorno

```bash
sudo cp .env.example .env
sudo cp blockchain-services/.env.example blockchain-services/.env
```

## Paso 3 — Editar `.env` y `blockchain-services/.env`

Valores mínimos a establecer (consulta la [guía de Docker Compose manual](instalar-compose-manual.md)
para la descripción completa de cada variable):

```env
# .env
SERVER_NAME=lab.tu-institucion.edu
ISSUER=
MYSQL_ROOT_PASSWORD=contraseña_segura
MYSQL_PASSWORD=contraseña_segura
GUAC_ADMIN_USER=admin
GUAC_ADMIN_PASS=contraseña_segura
ADMIN_ACCESS_TOKEN=token_aleatorio
LAB_MANAGER_TOKEN=token_aleatorio
LAB_MANAGER_ALLOWED_CIDRS=
LAB_ADMIN_BACKEND_URL=
LAB_ADMIN_BACKEND_TOKEN=
CORS_ALLOWED_ORIGINS=https://marketplace-decentralabs.vercel.app
FMU_JWT_AUDIENCE=https://lab.tu-institucion.edu/fmu
```

```env
# blockchain-services/.env
CONTRACT_ADDRESS=0xTuDireccionDeContrato
ETHEREUM_SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
FEATURES_PROVIDERS_ENABLED=true
FEATURES_PROVIDERS_REGISTRATION_ENABLED=true
ALLOWED_ORIGINS=https://lab.tu-institucion.edu,https://marketplace-decentralabs.vercel.app
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem
```

Mantén los valores de orquestacion Gateway/OpenResty solo en `.env`. El `docker-compose.yml` raiz inyecta esos valores al backend embebido desde `.env`.

Para un despliegue standalone de `blockchain-services` no gestionado por este Compose del Gateway, configura el `.env` propio de ese servicio standalone con su
`LAB_MANAGER_TOKEN` y, si procede, `LAB_MANAGER_ALLOWED_CIDRS`.

## Paso 4 — Aplicar la configuración NixOS

El flake incluye una configuración de host NixOS lista para usar en `nixosConfigurations.gateway`.
Importa tu `/etc/nixos/configuration.nix` existente y añade el módulo del gateway encima,
conservando los ajustes específicos del host (gestor de arranque, usuarios, discos, hardware).

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
```

Este comando:

1. Construye el cierre del sistema (puede tardar varios minutos en la primera ejecución).
2. Registra `lab-gateway.service` en systemd.
3. Arranca todos los servicios de Docker Compose gestionados por esa unidad.

## Paso 5 — Verificar el servicio

```bash
systemctl status lab-gateway.service
```

Comprueba el estado de salud:

```bash
curl -k https://localhost/health
```

## Paso 6 — Usar el módulo NixOS directamente

Si quieres incluir el gateway en tu propio flake en lugar de usar
`nixosConfigurations.gateway`, importa el módulo:

```nix
{
  inputs.lab-gateway.url = "path:/srv/lab-gateway";

  outputs = { nixpkgs, lab-gateway, ... }: {
    nixosConfigurations.mi-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        lab-gateway.nixosModules.default
        {
          services.lab-gateway = {
            enable = true;
            projectDir = "/srv/lab-gateway";
            envFile = "/srv/lab-gateway/.env";
            # Descomenta para habilitar el perfil de Cloudflare Tunnel:
            # profiles = [ "cloudflare" ];
          };
        }
      ];
    };
  };
}
```

## Paso 7 — Crear la cartera institucional

1. Abre `https://lab.tu-institucion.edu/wallet-dashboard`.
2. Introduce el `ADMIN_ACCESS_TOKEN` definido en `.env`.
3. Crea o importa la cartera institucional.

## Paso 8 — Actualizar el despliegue

Para aplicar cambios después de editar `.env` o descargar una nueva versión:

```bash
cd /srv/lab-gateway
sudo git pull --recurse-submodules
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
```

La unidad systemd reiniciará el stack de Compose automáticamente si el flake cambia.

## Comandos útiles

```bash
# Ver los logs del servicio en tiempo real
journalctl -u lab-gateway.service -f

# Reiniciar el stack del gateway
systemctl restart lab-gateway.service

# Detener el stack del gateway
systemctl stop lab-gateway.service

# Inspeccionar contenedores individuales
cd /srv/lab-gateway
docker compose ps
docker compose logs -f blockchain-services
```

## Próximos pasos

- [Tutorial de operador de extremo a extremo](../tutorials/tutorial-primera-sesion-laboratorio.md)
- [Guía de federación eduGAIN](../edugain/edugain-federacion.md)
