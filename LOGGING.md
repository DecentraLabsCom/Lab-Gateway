# Logging Guide

This project uses Docker `json-file` logging with per-service rotation in `docker-compose.yml`.

## Rotation limits

| Service | max-size | max-file | Approx max |
| --- | --- | --- | --- |
| `blockchain-services` | `20m` | `5` | ~100 MB |
| `openresty` | `10m` | `5` | ~50 MB |
| `mysql` | `10m` | `3` | ~30 MB |
| `guacamole` | `20m` | `5` | ~100 MB |
| `guacd` | `5m` | `3` | ~15 MB |
| `ops-worker` | `10m` | `3` | ~30 MB |

Estimated capped total (configured services): ~325 MB.

## Common commands

```bash
# All services (follow)
docker compose logs -f

# One service
docker compose logs -f openresty

# Last lines
docker compose logs --tail=100 guacamole

# Time window
docker compose logs --since=10m
```

## Search examples

PowerShell:

```powershell
docker compose logs | Select-String -Pattern "error|failed|exception" -CaseSensitive:$false
docker compose logs openresty | Select-String -Pattern "jwt|token|auth" -CaseSensitive:$false
```

Bash:

```bash
docker compose logs | grep -Ei "error|failed|exception"
docker compose logs openresty | grep -Ei "jwt|token|auth"
```

## Export logs

PowerShell:

```powershell
docker compose logs > gateway-logs-$(Get-Date -Format "yyyy-MM-dd").log
```

Bash:

```bash
docker compose logs > gateway-logs-$(date +%F).log
```

## Notes

- Rotation deletes older files automatically after the limits above.
- Host log file locations are Docker defaults (`/var/lib/docker/containers/...` on Linux).
- For production centralization, use a logging driver (for example `fluentd`) in compose.
