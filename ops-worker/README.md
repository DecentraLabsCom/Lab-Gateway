# Ops Worker for Lab Station Integration

This service handles remote lab host operations for the gateway:

- Wake-on-LAN and reachability checks.
- Remote LabStation command execution over WinRM.
- Heartbeat polling and persistence in MySQL.
- Optional reservation automation (start/end orchestration).

## Main components

- `worker.py`: Flask API and scheduler.
- `hosts.json` (`OPS_CONFIG`): host inventory and credentials references.
- MySQL tables from `mysql/001-create-schema.sql` and `mysql/002-labstation-ops.sql`.

## Quick start (dev)

```bash
cd ops-worker
python -m venv .venv
. .venv/Scripts/activate  # or: source .venv/bin/activate
pip install -r requirements.txt

export OPS_BIND=0.0.0.0
export OPS_PORT=8081
export OPS_CONFIG=hosts.json
export MYSQL_DSN="mysql+pymysql://user:pass@mysql:3306/guacamole_db"
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

## Deployment notes

- OpenResty proxies `/ops/` to this service.
- `/ops/` requires `LAB_MANAGER_TOKEN` via `X-Lab-Manager-Token` header or `lab_manager_token` cookie.
- **Network restriction**: OpenResty allows `/ops/` only from `127.0.0.1` and `172.16.0.0/12` (enforced before token validation).
  - Lab Manager UI (`/lab-manager`) works from any network with valid token.
  - Lab Station operations (`/ops` API) require access from gateway server or private networks.
  - When accessing Lab Manager remotely, ops features will show a network restriction warning.
- Prefer `env:VAR_NAME` in `hosts.json` for WinRM credentials.
- Keep `hosts.json` secrets out of git.
