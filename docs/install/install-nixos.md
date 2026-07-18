# Installation Guide — NixOS (Compose-managed Host)

Use this guide to deploy Lab Gateway on a dedicated NixOS machine using the included
`flake.nix`. This mode manages both the operating system and all gateway services
declaratively through systemd.

> **Scope**: this guide covers `nixosConfigurations.gateway` — the single supported NixOS
> deployment path. Componentised NixOS paths and deterministic image bundles were
> evaluated and removed from active scope; this compose-managed approach is the
> production baseline.

## Prerequisites

- A machine or VM running a current NixOS release compatible with the flake's
  `nixos-unstable` input, with flakes enabled. Pin the input for reproducible
  production rollouts instead of relying on an unpinned channel.
- Internet access from the target host (to pull flake inputs and container images).
- `git` available on the target host.

Enable flakes (add to `/etc/nixos/configuration.nix` if not already set):

```nix
nix.settings.experimental-features = [ "nix-command" "flakes" ];
```

## Step 1 — Place the repository on the target host

```bash
sudo mkdir -p /srv
sudo git clone --recurse-submodules https://github.com/DecentraLabsCom/Lab-Gateway.git /srv/lab-gateway
cd /srv/lab-gateway
```

## Step 2 — Create environment files

```bash
sudo cp .env.example .env
sudo cp blockchain-services/.env.example blockchain-services/.env
```

## Step 3 — Edit `.env` and `blockchain-services/.env`

Minimum values to set (see [Manual Docker Compose guide](install-manual-compose.md) for
the full description of each variable):

```env
# .env
SERVER_NAME=lab.your-institution.edu
# Leave ISSUER empty for Full mode. Set it to https://<full-gateway>/auth for Lite mode.
ISSUER=
BLOCKCHAIN_SERVICES_ENABLED=auto
MYSQL_ROOT_PASSWORD=strong_password
GUACAMOLE_MYSQL_PASSWORD=strong_password
BLOCKCHAIN_MYSQL_PASSWORD=strong_password
OPS_BACKEND_MYSQL_PASSWORD=strong_password
OPS_GUACAMOLE_MYSQL_PASSWORD=strong_password
GUACAMOLE_MYSQL_USER=guacamole_app
BLOCKCHAIN_MYSQL_USER=blockchain_app
OPS_BACKEND_MYSQL_USER=ops_backend
OPS_GUACAMOLE_MYSQL_USER=ops_guac
GUAC_ADMIN_USER=admin
GUAC_ADMIN_PASS=strong_password
ADMIN_ACCESS_TOKEN=random_token
LAB_MANAGER_TOKEN=random_token
# Optional: restrict /lab-admin backend calls authenticated with LAB_MANAGER_TOKEN.
# For Full + multiple Lite gateways, list the Lite gateway source IPs/CIDRs here.
LAB_MANAGER_ALLOWED_CIDRS=
# Lite only: set these when this Lite gateway must delegate lab publishing/update
# operations to a remote Full/standalone blockchain-services backend.
LAB_ADMIN_BACKEND_URL=
LAB_ADMIN_BACKEND_TOKEN=
CORS_ALLOWED_ORIGINS=https://marketplace-decentralabs.vercel.app
FMU_JWT_AUDIENCE=https://lab.your-institution.edu/fmu
```

```env
# blockchain-services/.env
CONTRACT_ADDRESS=0xYourContractAddress
ETHEREUM_SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
FEATURES_PROVIDERS_ENABLED=true
FEATURES_PROVIDERS_REGISTRATION_ENABLED=true
ALLOWED_ORIGINS=https://lab.your-institution.edu,https://marketplace-decentralabs.vercel.app
MARKETPLACE_PUBLIC_KEY_URL=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem
```

Keep Gateway/OpenResty orchestration values only in `.env`. The root `docker-compose.yml` injects those values into the embedded backend from `.env`.

In Lite mode, the embedded backend is not the local JWT authority: OpenResty
blocks its `/auth` issuer routes and trusts the remote `ISSUER`. For composite
Full + N Lite or standalone-backend + N Lite deployments, provision each Lite
with its own trust bundle and remote provisioner route. See
[Deployment Architectures](../deployment-architectures.md).

For a standalone `blockchain-services` deployment not managed by this Gateway compose stack, configure that standalone service's own `.env` with its `LAB_MANAGER_TOKEN` and, if desired, `LAB_MANAGER_ALLOWED_CIDRS`.

## Step 4 — Apply the NixOS configuration

The flake ships a ready-to-use NixOS host configuration at `nixosConfigurations.gateway`.
It imports your existing `/etc/nixos/configuration.nix` and layers the gateway module on top,
preserving your host-specific settings (bootloader, users, disks, hardware).

```bash
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
```

This command will:

1. Build the system closure (may take several minutes on first run).
2. Register `lab-gateway.service` with systemd.
3. Start all Docker Compose services managed by that unit.

## Step 5 — Verify the service

```bash
systemctl status lab-gateway.service
```

Check health:

```bash
curl -k https://localhost/health
```

## Step 6 — Using the NixOS module directly

If you want to include the gateway in your own flake rather than using
`nixosConfigurations.gateway`, import the module:

```nix
{
  inputs.lab-gateway.url = "path:/srv/lab-gateway";

  outputs = { nixpkgs, lab-gateway, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        lab-gateway.nixosModules.default
        {
          services.lab-gateway = {
            enable = true;
            projectDir = "/srv/lab-gateway";
            envFile = "/srv/lab-gateway/.env";
            # Uncomment to enable Cloudflare Tunnel profile:
            # profiles = [ "cloudflare" ];
          };
        }
      ];
    };
  };
}
```

## Step 7 — Create the institutional wallet

1. Open `https://lab.your-institution.edu/wallet-dashboard`.
2. Enter the `ADMIN_ACCESS_TOKEN` from `.env`.
3. Create or import the institutional wallet.

## Step 8 — Updating the deployment

To apply changes after editing `.env` or pulling a new version:

```bash
cd /srv/lab-gateway
sudo git pull --recurse-submodules
sudo nixos-rebuild switch --flake /srv/lab-gateway#gateway
```

The systemd unit will restart the Compose stack automatically if the flake changes.

## Useful commands

```bash
# View live service logs
journalctl -u lab-gateway.service -f

# Restart the gateway stack
systemctl restart lab-gateway.service

# Stop the gateway stack
systemctl stop lab-gateway.service

# Inspect individual containers
cd /srv/lab-gateway
docker compose ps
docker compose logs -f blockchain-services
```

## Next steps

- [End-to-end operator tutorial](../tutorials/tutorial-first-lab-session.md)
- [eduGAIN federation guide](../edugain/edugain-federation.md)
