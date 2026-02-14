# Guia de Instalacion (Espanol)

Esta guia resume las modalidades soportadas de despliegue del DecentraLabs Gateway.

## 1. Elegir modalidad

1. Script de setup: `setup.sh` / `setup.bat` (recomendado en primera instalacion).
2. Docker Compose manual.
3. Host NixOS gestionado con compose (`#gateway`).

## 2. Requisitos previos

- Git
- Docker Engine
- Docker Compose plugin (`docker compose`)
- Certificados TLS para produccion (`certs/fullchain.pem`, `certs/privkey.pem`)
- Submodulo `blockchain-services` inicializado

Opcional:

- Nix (modo 3)
- Host NixOS (modo 3)

## 3. Preparacion comun

```bash
git clone https://github.com/DecentraLabsCom/lite-lab-gateway.git
cd lite-lab-gateway
git submodule update --init --recursive
cp .env.example .env
cp blockchain-services/.env.example blockchain-services/.env
```

Despues edita `.env` y `blockchain-services/.env`.

## 4. Modo A: Script de setup

Linux/macOS:

```bash
chmod +x setup.sh
./setup.sh
```

Windows:

```powershell
.\setup.bat
```

## 5. Modo B: Docker Compose manual

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f openresty
```

## 6. Modo C: Host NixOS gestionado con compose

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
systemctl status lab-gateway.service
```

## 7. Validacion post-instalacion

```bash
curl -k https://127.0.0.1/health
curl -k https://127.0.0.1/gateway/health
```

Pruebas opcionales:

```bash
./tests/integration/run-integration.sh
./tests/smoke/run-smoke.sh
```

## 8. Resolucion de problemas

- Submodulo no inicializado: ejecutar `git submodule update --init --recursive`.
- Faltan certificados: agregar certs o usar fallback local autosignado.
- Permisos en bind mounts: revisar propietario de `certs/` y `blockchain-data/`.
- Servicio no accesible: revisar `docker compose logs -f` o `journalctl -u lab-gateway.service -f` (modo NixOS).
