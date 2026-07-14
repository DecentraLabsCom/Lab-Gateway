# Documentation index

Start with [DecentraLabs Gateway](README.md) and [Deployment Architectures](docs/deployment-architectures.md). The architecture guide is the reference for Full, Lite, Full + N Lite and standalone `blockchain-services` + N Lite deployments.

## Access and architecture

- [Deployment Architectures](docs/deployment-architectures.md)
- [Laboratory Connectivity](docs/workflows/laboratory-connectivity.md)
- [Guacamole Session Policy](docs/guacamole-session-policy.md)
- [Guacamole Connections](configuring-lab-connections/guacamole-connections.md)
- [Logging Configuration](LOGGING.md)

## End-to-end workflows

- [Institutional Reservation Workflow](docs/workflows/institutional-reservation-workflow.md)
- [Institutional Check-in, Lab Access, and Session Workflow](docs/workflows/institutional-check-in-access-sessions.md)
- [Lab Gateway and Lab Station Operations](docs/workflows/gateway-lab-station-operations.md)
- [First Lab Session tutorial (EN)](docs/tutorials/tutorial-first-lab-session.md)
- [Tutorial de primera sesión (ES)](docs/tutorials/tutorial-primera-sesion-laboratorio.md)

## Installation

- [Setup Script (EN)](docs/install/install-setup-script.md)
- [Setup Script (ES)](docs/install/instalar-setup-script.md)
- [Manual Docker Compose (EN)](docs/install/install-manual-compose.md)
- [Docker Compose manual (ES)](docs/install/instalar-compose-manual.md)
- [NixOS (EN)](docs/install/install-nixos.md)
- [NixOS (ES)](docs/install/instalar-nixos.md)
- [Certbot / ACME](certbot/README.md)

## Federation and backend services

- [eduGAIN Federation (EN)](docs/edugain/edugain-federation.md)
- [Federación eduGAIN (ES)](docs/edugain/edugain-federacion.md)
- [Ops Worker](ops-worker/README.md)

## FMU and native proxy

- [FMU Runner](fmu-runner/README.md)
- [FMU data layout](fmu-data/README.md)
- [FMU proxy runtime](fmu-proxy-runtime/README.md)
- [FMU proxy runtime source](fmu-proxy-runtime-src/README.md)
- [FMU proxy runtime architecture](fmu-proxy-runtime-src/ARCHITECTURE.md)

## Verification

- [OpenResty Lua unit tests](openresty/tests/README.md)
- [Integration tests](tests/integration/README.md)

English and Spanish guides should describe the same deployment contract. When
they diverge, verify `docker-compose.yml`, `.env.example`, setup scripts and
the executable service configuration before editing the prose.
