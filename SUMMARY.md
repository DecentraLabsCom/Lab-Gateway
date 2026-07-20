# Lab Gateway documentation index

Begin with [Lab Gateway](README.md) and the [documentation guide](docs/README.md).
The guide routes every task to one primary document; use this file as a compact
table of contents.

## Getting started and deployment

- [Documentation guide](docs/README.md)
- [Deployment architectures](docs/deployment-architectures.md)
- [Configuration reference](docs/reference/configuration.md)
- Installation
  - [Setup script (EN)](docs/install/install-setup-script.md)
  - [Script de configuración (ES)](docs/install/instalar-setup-script.md)
  - [Manual Docker Compose (EN)](docs/install/install-manual-compose.md)
  - [Docker Compose manual (ES)](docs/install/instalar-compose-manual.md)
  - [NixOS (EN)](docs/install/install-nixos.md)
  - [NixOS (ES)](docs/install/instalar-nixos.md)
  - [Certbot / ACME](certbot/README.md)

## Architecture and connectivity

- [Laboratory connectivity](docs/workflows/laboratory-connectivity.md)
- [Gateway and Lab Station operations](docs/workflows/gateway-lab-station-operations.md)
- [Guacamole connections](docs/configuring-lab-connections/guacamole-connections.md)
- [Guacamole session policy](docs/guacamole-session-policy.md)
- [Logging configuration](LOGGING.md)

## Institutional workflows

- [Institutional reservation workflow](docs/workflows/institutional-reservation-workflow.md)
- [Check-in, lab access, and session workflow](docs/workflows/institutional-check-in-access-sessions.md)
- [eduGAIN federation (EN)](docs/edugain/edugain-federation.md)
- [Federación eduGAIN (ES)](docs/edugain/edugain-federacion.md)
- [First lab session tutorial (EN)](docs/tutorials/tutorial-first-lab-session.md)
- [Tutorial de primera sesión (ES)](docs/tutorials/tutorial-primera-sesion-laboratorio.md)

## Digital twins

- [FMI/FMU support](docs/fmi-fmu-support.md)
- [AAS support](docs/aas-support.md)
- [FMU Runner](fmu-runner/README.md)
- [FMU data layout](fmu-data/README.md)
- [FMU proxy runtime](fmu-proxy-runtime/README.md)
- [FMU proxy runtime source](fmu-proxy-runtime-src/README.md)
- [FMU proxy runtime architecture](fmu-proxy-runtime-src/ARCHITECTURE.md)

## Operations and verification

- [Operations and health](docs/reference/operations-and-health.md)
- [Ops Worker](ops-worker/README.md)
- [OpenResty Lua unit tests](openresty/tests/README.md)
- [Integration tests](tests/integration/README.md)

## Embedded backend

The embedded canonical backend lives in `blockchain-services/`. Its detailed
API, security, wallet, deployment, and operations documentation starts at
[blockchain-services documentation](blockchain-services/SUMMARY.md).
