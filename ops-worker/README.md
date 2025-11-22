# Ops Worker for Lab Station Integration

This lightweight worker centralizes the operational tasks the Lab Gateway needs to perform on Lab Station hosts:

- Send Wake-on-LAN and validate boot (ping with retries).
- Execute `LabStation.exe` commands via WinRM (`prepare-session`, `release-session --reboot`, `session guard`, `power shutdown|hibernate`, `status-json`, `recovery reboot-if-needed`).
- Poll `heartbeat.json` (and optionally `session-guard-events.jsonl`) and persist denormalized fields for the UI/alerts.

## Components

- `worker.py`: Flask API exposing `/api/wol`, `/api/winrm`, `/api/heartbeat/poll`.
- Scheduler (optional) runs inside the worker to poll heartbeats periodically when `OPS_POLL_ENABLED=true`.
- MySQL persistence for host catalog and heartbeat snapshots (see `mysql/005-labstation-ops.sql`).

## Quick start (dev)

```bash
cd ops-worker
python -m venv .venv
. .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
export OPS_BIND=0.0.0.0
export OPS_PORT=8081
export OPS_CONFIG=hosts.json
export MYSQL_DSN="mysql+pymysql://user:pass@mysql:3306/lab_gateway"
export OPS_POLL_ENABLED=true
export OPS_POLL_INTERVAL=60
python worker.py
```

`hosts.json` (example, copy from `hosts.sample.json` and edit secrets):

```json
{
  "hosts": [
    {
      "name": "lab-ws-01",
      "address": "lab-ws-01",
      "mac": "00:11:22:33:44:55",
      "winrm_user": "LABSTATION\\LabGatewaySvc",
      "winrm_pass": "********",
      "winrm_transport": "ntlm",
      "heartbeat_path": "C:\\\\LabStation\\\\labstation\\\\data\\\\telemetry\\\\heartbeat.json",
      "events_path": "C:\\\\LabStation\\\\labstation\\\\data\\\\telemetry\\\\session-guard-events.jsonl"
    }
  ]
}
```

## Smoke tests (curl)

```bash
# Health
curl -s http://localhost:8081/health

# Wake-on-LAN + ping
curl -s -XPOST http://localhost:8081/api/wol -H "Content-Type: application/json" -d '{"host":"lab-ws-01"}'

# Heartbeat poll (persists to MySQL when configured)
curl -s -XPOST http://localhost:8081/api/heartbeat/poll -H "Content-Type: application/json" -d '{"host":"lab-ws-01"}'

# Run LabStation.exe prepare-session via WinRM
curl -s -XPOST http://localhost:8081/api/winrm -H "Content-Type: application/json" -d '{"host":"lab-ws-01","command":"prepare-session","args":["--guard-grace=90"]}'
```

## API (internal)

- `POST /api/wol` → `{ host, mac?, broadcast?, port?, ping_target?, ping_timeout?, attempts? }`
- `POST /api/winrm` → `{ host, command, args?, user?, password?, transport?, use_ssl?, port? }`
  - Builds and runs `C:\LabStation\LabStation.exe <command> <args>` via PowerShell/WinRM.
- `POST /api/heartbeat/poll` → `{ host }`
  - Reads `heartbeat.json` via WinRM (`Get-Content -Raw`) and upserts into MySQL.
- `POST /api/reservations/start` → `{ reservationId, host, labId?, wake?, wakeOptions?, prepare?, prepareArgs?, guardGrace? }`
  - Sends WoL + ping validation (unless `wake=false`), then runs `prepare-session` with configurable args. Each step logs into `reservation_operations`.
- `POST /api/reservations/end` → `{ reservationId, host, labId?, release?, releaseArgs?, powerAction? }`
  - Runs `release-session` (defaults to `--reboot`) and optional `power shutdown|hibernate` with args, logging outcomes per reservation.

Responses include `duration_ms`, stdout/stderr, parsed JSON (when applicable), and DB persistence status.

## Scheduler

Enable with `OPS_POLL_ENABLED=true` (env) and set `OPS_POLL_INTERVAL=60` (seconds). The worker will:

- Iterate configured hosts in `hosts.json`.
- Fetch heartbeat and latest session-guard event line.
- Upsert host catalog + insert heartbeat snapshot.

## Deployment notes

- OpenResty proxies `/ops/` to this service (see `openresty/lab_access.conf`).
- Use a dedicated network-only account for WinRM (`SeDenyInteractiveLogonRight` on the host).
- Keep secrets outside git; `hosts.json` is gitignored on purpose.
