# Installation Guide (English)

This guide consolidates installation options for DecentraLabs Gateway.

## 1. Choose a Deployment Mode

1. Setup script: `setup.sh` / `setup.bat` (recommended first deployment).
2. Docker Compose manual mode.
3. Nix wrapper for compose (`nix run .#lab-gateway-docker`).
4. NixOS compose-managed host (`#gateway`).
5. NixOS componentized host (`#gateway-components`).

## 2. Prerequisites

- Git
- Docker Engine
- Docker Compose plugin (`docker compose`)
- TLS certs for production (`certs/fullchain.pem`, `certs/privkey.pem`)
- `blockchain-services` submodule initialized

Optional:

- Nix (for modes 3, 4, 5)
- NixOS host (for modes 4, 5)

## 3. Common Initial Setup

```bash
git clone https://github.com/DecentraLabsCom/lite-lab-gateway.git
cd lite-lab-gateway
git submodule update --init --recursive
cp .env.example .env
cp blockchain-services/.env.example blockchain-services/.env
```

Then edit `.env` and `blockchain-services/.env`.

## 4. Mode A: Setup Script

Linux/macOS:

```bash
chmod +x setup.sh
./setup.sh
```

Windows:

```powershell
.\setup.bat
```

## 5. Mode B: Docker Compose Manual

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f openresty
```

## 6. Mode C: Nix Wrapper for Compose

```bash
nix run .#lab-gateway-docker -- --project-dir "$PWD" --env-file "$PWD/.env" up -d --build
```

Stop:

```bash
nix run .#lab-gateway-docker -- --project-dir "$PWD" --env-file "$PWD/.env" down
```

## 7. Mode D: NixOS Compose-managed Host

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
systemctl status lab-gateway.service
```

## 8. Mode E: NixOS Componentized Host

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway-components
systemctl status docker-openresty.service
```

If reservation automation is needed in this mode, set:

- `services.lab-gateway-components.opsMysqlDsn`

## 9. Post-install Validation

```bash
curl -k https://127.0.0.1/health
curl -k https://127.0.0.1/gateway/health
```

Optional tests:

```bash
./tests/integration/run-integration.sh
./tests/smoke/run-smoke.sh
```

## 10. Troubleshooting

- Submodule not initialized: run `git submodule update --init --recursive`.
- Missing cert files: add certs or use self-signed local fallback.
- Permission issues on bind mounts: verify ownership for `certs/` and `blockchain-data/`.
- Service not reachable: inspect `docker compose logs -f` or `journalctl -u docker-openresty -f` (NixOS componentized mode).
