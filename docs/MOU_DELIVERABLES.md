# MoU Deliverables Status

Last updated: 2026-02-13

This file tracks Annex I deliverables from the Vietsch MoU and maps each one to repository evidence and required external actions.

## Status Legend

- `DONE-IN-REPO`: completed with code/docs in this repository.
- `IN-PROGRESS-IN-REPO`: partially implemented in this repository.
- `EXTERNAL-ACTION-REQUIRED`: requires deployment, partner coordination, or federation processes outside git.

## Deliverables Matrix

| Deliverable | Status | Evidence in this repo | Remaining work |
| --- | --- | --- | --- |
| D1. NixOS configuration and modules for the gateway | IN-PROGRESS-IN-REPO | `flake.nix`, `nix/nixos-module.nix`, `nix/nixos-components-module.nix`, `nix/hosts/gateway.nix` | Increase component determinism for all images (OpenResty/Guacamole/blockchain-services) from Nix expressions. |
| D2. Deterministic Docker image from same config | IN-PROGRESS-IN-REPO | `nix/images/ops-worker-image.nix`, `flake.nix` package `lab-gateway-ops-worker-image` | Extend deterministic image builds to all gateway components. |
| D3. Installation and usage docs/tutorials (EN/ES) | DONE-IN-REPO | `README.md`, docs under `docs/install`, `docs/edugain`, `docs/tutorials` | Record and publish video tutorial externally. |
| D4. Two pilots and feedback incorporation | EXTERNAL-ACTION-REQUIRED | Pilot runbook and templates under `docs/pilots` | Execute pilots in real institutions and commit resulting reports/findings. |
| D5. Public release package (v1.0) with final artifacts | IN-PROGRESS-IN-REPO | Flake outputs, CI additions, docs pack | Tag/release process and artifact publication. |
| D6. Start eduGAIN registration process via NREN | EXTERNAL-ACTION-REQUIRED | eduGAIN technical guide in `docs/edugain` | Complete institutional coordination and submit federation metadata through RedIRIS/NREN. |
| D7. Release versions after pilots (NixOS + container) | IN-PROGRESS-IN-REPO | Branch work for NixOS and container pathways | Merge pilot feedback and publish tagged v1.0 release artifacts. |

## Immediate Repository Backlog

1. Create deterministic Nix-built images for OpenResty, Guacamole, and blockchain-services.
2. Add CI checks that evaluate NixOS configurations and build all Nix image outputs.
3. Add a release checklist and versioned release notes for v1.0.

## External Backlog (Non-git execution)

1. Run UNED pilot and fill `docs/pilots/UNED_PILOT_REPORT_TEMPLATE.md`.
2. Run partner pilot and fill `docs/pilots/PARTNER_PILOT_REPORT_TEMPLATE.md`.
3. Submit eduGAIN registration package with RedIRIS/NREN and archive confirmation references in docs.
