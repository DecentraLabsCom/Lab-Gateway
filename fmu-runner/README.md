# FMU Runner

FastAPI service that executes FMU simulations via [FMPy](https://github.com/CATIA-Systems/FMPy).
Runs as a Docker container inside the Lab Gateway stack, protected by OpenResty JWT validation.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/api/v1/fmu/list` | Return authorised provisioned FMU |
| GET | `/api/v1/fmu/proxy/{labId}?reservationKey=...` | Auto-generate reservation-scoped `proxy.fmu` |
| GET | `/api/v1/simulations/describe?fmuFileName=<file>` | Read FMU model description |
| POST | `/api/v1/simulations/run` | Execute a simulation |
| WS | `/api/v1/fmu/sessions` | Realtime FMU session API (`requestId`, `model.describe`, control, subscribe/unsubscribe, ping/pong) |
| WS (internal) | `/internal/fmu/sessions` | Internal realtime channel (optional `x-internal-session-token`) |

## Unit Tests

Tests use **pytest** + **FastAPI TestClient** (httpx). FMPy and JWT auth are mocked,
so no real FMU files or running services are required.

### Prerequisites

```bash
# From fmu-runner/
pip install fastapi uvicorn fmpy pyjwt[crypto] httpx pydantic pytest httpx numpy
```

Or install from requirements (adding test deps):

```bash
pip install -r requirements.txt pytest numpy
```

### Run

```bash
# From fmu-runner/ — recommended
cd fmu-runner
pytest

# Verbose
pytest -v

# From root of Lab Gateway (also works thanks to conftest.py sys.path fix)
pytest fmu-runner/
```

### Test coverage

| Test | What it validates |
|------|------------------|
| `test_health_returns_up` | `/health` returns `{"status": "UP"}` |
| `test_describe_returns_model_metadata` | `/describe` parses FMPy model description |
| `test_describe_requires_fmuFileName` | Missing query param → 422 |
| `test_run_executes_simulation` | Happy-path simulation returns structured result |
| `test_run_rejects_invalid_time_range` | stopTime ≤ startTime → 400 |
| `test_run_rejects_zero_step_size` | stepSize ≤ 0 → 400 |
| `test_run_rejects_missing_access_key` | JWT without accessKey → 400 |
| `test_run_returns_429_when_concurrency_exceeded` | Concurrency limit → 429 |

## Docker

Built and started automatically by `docker-compose.yml` in the Lab Gateway root.

```bash
# From Lab Gateway root
docker compose up --build fmu-runner
```

FMU files are mounted from `./fmu-data` into `/fmu-data` inside the container.
See [fmu-data/README.md](../fmu-data/README.md) for the expected directory layout.

Marketplace upload is disabled by design. The runner only serves FMUs already present
under `FMU_DATA_PATH`.

## Realtime WS Notes

- Every client command must include `requestId` (idempotent replay support).
- `session.terminate` is idempotent.
- `sim.outputs` includes `seq` and `dropped` for backpressure visibility.
- Keepalive/telemetry events: `session.pong`, `session.heartbeat`, `session.expiring`.
- `session.create` accepts `sessionTicket` (one-shot) when no bearer token is provided.
- Explicit rate limits:
  - Proxy download endpoint (`PROXY_DOWNLOAD_RATE_LIMIT_PER_MINUTE`, default `20`)
  - Realtime `session.create` (`WS_CREATE_RATE_LIMIT_PER_MINUTE`, default `30`)
- Proxy artifact integrity headers:
  - `X-Proxy-Artifact-Sha256` always present.
  - `X-Proxy-Artifact-Signature` present when `FMU_PROXY_SIGNING_KEY` is configured.
