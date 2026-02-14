# Installation Guide (English)

This guide consolidates the supported installation options for DecentraLabs Gateway.

## 1. Choose a Deployment Mode

1. Setup script: `setup.sh` / `setup.bat` (recommended first deployment).
2. Docker Compose manual mode.
3. NixOS compose-managed host (`#gateway`).

## 2. Prerequisites

- Git
- Docker Engine
- Docker Compose plugin (`docker compose`)
- TLS certs for production (`certs/fullchain.pem`, `certs/privkey.pem`)
- `blockchain-services` submodule initialized

Optional:

- Nix (for mode 3)
- NixOS host (for mode 3)

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

## 6. Mode C: NixOS Compose-managed Host

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
systemctl status lab-gateway.service
```

## 7. Post-install Validation

```bash
curl -k https://127.0.0.1/health
curl -k https://127.0.0.1/gateway/health
```

Optional tests:

```bash
./tests/integration/run-integration.sh
./tests/smoke/run-smoke.sh
```

## 8. Troubleshooting

- Submodule not initialized: run `git submodule update --init --recursive`.
- Missing cert files: add certs or use self-signed local fallback.
- Permission issues on bind mounts: verify ownership for `certs/` and `blockchain-data/`.
- Service not reachable: inspect `docker compose logs -f` or `journalctl -u lab-gateway.service -f` (NixOS mode).
