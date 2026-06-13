# Ops Worker for Lab Station Integration

This service handles remote lab host operations for the gateway:

- Wake-on-LAN and reachability checks.
- Remote LabStation command execution over WinRM.
- Heartbeat polling and persistence in MySQL.
- Optional reservation automation (start/end orchestration).

## Main components

- `worker.py`: Flask API and scheduler.
- `hosts.json` (`OPS_CONFIG`): host inventory and credentials references.
- MySQL tables from `mysql/002-labstation-ops.sql`, stored in the `BLOCKCHAIN_MYSQL_DATABASE` schema alongside `lab_reservations`.

## Quick start (dev)

```bash
cd ops-worker
python -m venv .venv
. .venv/Scripts/activate  # or: source .venv/bin/activate
pip install -r requirements.txt

export OPS_BIND=0.0.0.0
export OPS_PORT=8081
export OPS_CONFIG=hosts.json
export MYSQL_DSN="mysql+pymysql://user:pass@mysql:3306/blockchain_services"
export OPS_POLL_ENABLED=true
export OPS_POLL_INTERVAL=60

python worker.py
```

## hosts.json example

Copy `hosts.sample.json` and replace credentials.

```json
{
  "hosts": [
    {
      "name": "lab-ws-01",
      "address": "lab-ws-01",
      "mac": "00:11:22:33:44:55",
      "winrm_user": "env:WINRM_USER_LAB_WS_01",
      "winrm_pass": "env:WINRM_PASS_LAB_WS_01",
      "winrm_transport": "ntlm",
      "heartbeat_path": "C:\\\\LabStation\\\\labstation\\\\data\\\\telemetry\\\\heartbeat.json",
      "events_path": "C:\\\\LabStation\\\\labstation\\\\data\\\\telemetry\\\\session-guard-events.jsonl",
      "labs": ["1"]
    }
  ]
}
```

## API (internal)

- `GET /health`
- `POST /api/wol`
  - Body: `{ host, mac?, broadcast?, port?, ping_target?, ping_timeout?, attempts? }`
- `POST /api/winrm`
  - Body: `{ host, command, args?, user?, password?, transport?, use_ssl?, port? }`
  - Runs `C:\LabStation\LabStation.exe <command> <args>` via WinRM.
- `POST /api/heartbeat/poll`
  - Body: `{ host, include_events? }`
- `GET /api/hosts`
  - Returns configured ops hosts plus auto-linked Guacamole connection metadata.
- `POST /api/hosts/discover`
  - Body: `{ connectionId }`
  - Probes a Guacamole connection candidate for DNS, WinRM, and optional Lab Station HTTP health.
- `POST /api/hosts/provision`
  - Body: `{ connectionId, name?, address?, mac?, labs?, winrmUserEnv, winrmPassEnv, heartbeatPath? }`
  - Re-runs discovery and only provisions candidates with Lab Station HTTP health or reachable WinRM.
  - Writes a dynamic host entry using `env:WINRM_*` references only; raw WinRM credentials are rejected.
- `POST /api/reservations/start`
  - Body: `{ reservationId, host, labId?, wake?, wakeOptions?, prepare?, prepareArgs?, guardGrace? }`
- `POST /api/reservations/end`
  - Body: `{ reservationId, host, labId?, release?, releaseArgs?, powerAction? }`
- `GET /api/reservations/timeline?reservationId=...&limit=...&offset=...`
- `POST /api/hosts/reload`
- `POST /api/hosts/quarantine`
  - Body: `{ host, quarantined }`

## Scheduler

Enable with:

- `OPS_POLL_ENABLED=true`
- `OPS_POLL_INTERVAL=60`

Reservation automation knobs:

- `OPS_RESERVATION_AUTOMATION` (compose default: `true`)
- `OPS_RESERVATION_SCAN_INTERVAL` (default `30`)
- `OPS_RESERVATION_START_LEAD` (default `120`)
- `OPS_RESERVATION_END_DELAY` (default `60`)
- `OPS_RESERVATION_LOOKBACK` (default `21600`)
- `OPS_RESERVATION_RETRY_COOLDOWN` (default `60`)

Notification integration knobs:

- `NOTIFICATION_SERVICE_URL` (default `http://blockchain-services:8080/billing/admin/notifications/send`)
- `NOTIFICATION_SERVICE_RECIPIENTS` (comma-separated recipients for failure alerts; optional if blockchain-services has `defaultTo` configured)
- `NOTIFICATION_SERVICE_RETRY_ATTEMPTS` (default `3`)
- `NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS` (default `5`)

Discovery knobs:

- `OPS_DISCOVERY_TIMEOUT_SECONDS` (default `1.5`)
- `OPS_DISCOVERY_WINRM_PORTS` (default `5985,5986`)
- `OPS_DISCOVERY_LABSTATION_PORTS` (default `8765,8088`)
- `OPS_DISCOVERY_LABSTATION_PATHS` (default `/labstation/health,/health`)

## Deployment notes

- OpenResty proxies `/ops/` to this service.
- `/ops/` requires `LAB_MANAGER_TOKEN` via `X-Lab-Manager-Token` header or `lab_manager_token` cookie.
- **Network restriction**: OpenResty allows `/ops/` only from loopback and RFC1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) before token validation.
  - Lab Manager UI (`/lab-manager`) works from any network with valid token.
  - Lab Station operations (`/ops` API) require access from gateway server or private networks.
  - When accessing Lab Manager remotely, ops features will show a network restriction warning.
- Container runtime uses `waitress` instead of the Flask development server.
- Prefer `env:VAR_NAME` in `hosts.json` for WinRM credentials.
- `OPS_CONFIG` is the base, usually read-only host catalog.
- `OPS_DYNAMIC_CONFIG` is the writable dynamic catalog used by Lab Manager provisioning; Docker Compose maps it to `./ops-data/hosts.json`.
- Store actual `WINRM_USER_*` and `WINRM_PASS_*` values in the service environment, not in either host catalog.
- Keep `hosts.json` and `ops-data/hosts.json` secrets out of git.
