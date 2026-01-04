# Ops Worker for Lab Station Integration

This lightweight worker centralizes the operational tasks the Lab Gateway needs to perform on Lab Station hosts:

- Send Wake-on-LAN and validate boot (ping with retries).
- Execute `LabStation.exe` commands via WinRM (`prepare-session`, `release-session --reboot`, `session guard`, `power shutdown|hibernate`, `status-json`, `recovery reboot-if-needed`).
- Poll `heartbeat.json` (and optionally `session-guard-events.jsonl`) and persist denormalized fields for the UI/alerts.

## Components

- `worker.py`: Flask API exposing `/api/wol`, `/api/winrm`, `/api/heartbeat/poll`.
- Scheduler (optional) runs inside the worker to poll heartbeats periodically when `OPS_POLL_ENABLED=true`.
- MySQL persistence for host catalog, heartbeat snapshots y operaciones de reserva (ver `mysql/005-labstation-ops.sql` y `mysql/004-auth-service-schema.sql`).
- `/ops/` se protege conis protected with `OPS_SECRET` (env). OpenResty sets cookie `ops_token` when serving `/lab-manager/` and validates cookie or header `X-Ops-Token` before proxying.

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
      "winrm_user": "env:WINRM_USER_LAB_WS_01",
      "winrm_pass": "env:WINRM_PASS_LAB_WS_01",
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
- If `OPS_RESERVATION_AUTOMATION=true`, it looks for reservations in `lab_reservations`, awakes/prepares/closes and persists `reservation_operations`.

## Reservation automation (optional)

`OPS_RESERVATION_AUTOMATION=true` (default value) lets the worker wake/prepare/release Lab Stations around each booking automatically. Requirements:

1. Every host entry in `hosts.json` must declare the blockchain lab IDs it can serve:

   ```json
   {
     "name": "lab-ws-01",
     "address": "lab-ws-01",
     "labs": ["1", "chemistry-lab"]
   }
   ```

2. `MYSQL_DSN` must point to the same database that contains the `lab_reservations` table (see `mysql/004-auth-service-schema.sql`).

When enabled, the worker:

- Looks ahead `OPS_RESERVATION_START_LEAD` seconds (default 120) and triggers `/api/reservations/start` once for CONFIRMED reservations; successful runs mark the DB row as `ACTIVE`.
- Waits `OPS_RESERVATION_END_DELAY` seconds (default 60) after the end time to invoke `/api/reservations/end`; successful runs mark the row as `COMPLETED`.
- Writes summary rows to `reservation_operations` using `action = "scheduler:start" | "scheduler:end"` so you can audit or retry.

Tuning knobs:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPS_RESERVATION_AUTOMATION` | `true` | Master toggle. |
| `OPS_RESERVATION_SCAN_INTERVAL` | `30` | How often to scan MySQL (seconds). |
| `OPS_RESERVATION_START_LEAD` | `120` | Seconds before `start_time` to prepare the host / lab station. |
| `OPS_RESERVATION_END_DELAY` | `60` | Seconds after `end_time` to release/power actions. |
| `OPS_RESERVATION_LOOKBACK` | `21600` | Maximum age (seconds) of reservations to consider when catching up. |
| `OPS_RESERVATION_RETRY_COOLDOWN` | `60` | Minimum seconds between scheduler attempts for the same reservation. |

## Deployment notes

- OpenResty proxies `/ops/` to this service (see `openresty/lab_access.conf`).
- Use a dedicated network-only account for WinRM (`SeDenyInteractiveLogonRight` on the host / lab station).
- Keep secrets outside git; `hosts.json` is gitignored on purpose.
- `/ops/` is gated by `OPS_SECRET` (env) and expects header `X-Ops-Token` or cookie `ops_token`.
- WinRM allowlist: set `OPS_ALLOWED_COMMANDS` (comma-separated) to restrict `/api/winrm` (default: `prepare-session,release-session,power,session,energy,status-json,recovery,account,service,wol,status`).
- WinRM timeouts: `OPS_WINRM_READ_TIMEOUT` and `OPS_WINRM_OPERATION_TIMEOUT` (seconds) configure the session.
- Credentials: prefer `env:VAR` in `hosts.json` for `winrm_user`/`winrm_pass` and set those env vars in the container (avoid plaintext in JSON).
- In OpenResty, `/lab-manager/` allows private networks by default and requires `LAB_MANAGER_INTERNAL_TOKEN` for non-private clients; `/ops/` remains limited to `127.0.0.1` and Docker private networks (`172.16.0.0/12`) and requires `OPS_SECRET`.
