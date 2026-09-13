import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from run_router import create_run_router


def _build_app(*, mode="local", claims=None, future=None):
    resolved_claims = claims or {
        "labId": "lab-1",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "accessKey": "model.fmu",
        "resourceType": "fmu",
    }
    local_future = future or Future()
    if future is None:
        local_future.set_result({"time": [0, 1], "output": [1.0, 2.0]})

    async def verify_jwt():
        return resolved_claims

    enforce_fmu_claim = MagicMock()
    ensure_local_backend = MagicMock()
    get_station_backend = MagicMock()
    request_payload = MagicMock(return_value={"labId": "lab-1", "simId": "sim-1"})
    extract_authorization = MagicMock(return_value="Bearer token")
    observation = AsyncMock(return_value=True)
    get_claim_lab_id = MagicMock(side_effect=lambda current_claims: current_claims.get("labId"))
    normalize_lab_id = MagicMock(side_effect=lambda value: str(value).strip() if value else None)
    enforce_reservation = MagicMock()
    resolve_fmu_path = MagicMock(return_value="/data/model.fmu")
    execution_options = SimpleNamespace(
        start_time=0.0,
        stop_time=1.0,
        step_size=0.1,
        timeout=2.0,
        fmi_type=None,
        solver_name=None,
    )
    parse_options = MagicMock(return_value=execution_options)
    resolve_fmi_type = MagicMock(return_value="CoSimulation")
    acquire_slot = MagicMock()
    submit_simulation = MagicMock(return_value=("executor", local_future))
    track_future = MagicMock()
    shutdown_executor = MagicMock()
    finalize_tracking = MagicMock()
    save_history = AsyncMock()
    new_simulation_id = MagicMock(return_value="sim-1")
    monotonic = MagicMock(side_effect=[100.0, 100.25])
    logger = MagicMock()

    app = FastAPI()
    app.include_router(create_run_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        get_backend_mode=lambda: mode,
        get_station_backend=get_station_backend,
        simulation_request_payload=request_payload,
        extract_authorization_header=extract_authorization,
        record_browser_session_started=observation,
        ensure_local_execution_backend=ensure_local_backend,
        get_claim_lab_id=get_claim_lab_id,
        normalize_lab_id=normalize_lab_id,
        enforce_requested_reservation=enforce_reservation,
        resolve_fmu_path=resolve_fmu_path,
        parse_simulation_options=parse_options,
        resolve_fmi_type=resolve_fmi_type,
        acquire_slot=acquire_slot,
        new_simulation_id=new_simulation_id,
        monotonic=monotonic,
        submit_simulation=submit_simulation,
        track_running_future=track_future,
        shutdown_executor=shutdown_executor,
        finalize_tracking=finalize_tracking,
        save_history=save_history,
        logger=logger,
    ))
    return {
        "client": TestClient(app),
        "future": local_future,
        "enforce_fmu_claim": enforce_fmu_claim,
        "ensure_local_backend": ensure_local_backend,
        "get_station_backend": get_station_backend,
        "request_payload": request_payload,
        "extract_authorization": extract_authorization,
        "observation": observation,
        "get_claim_lab_id": get_claim_lab_id,
        "normalize_lab_id": normalize_lab_id,
        "enforce_reservation": enforce_reservation,
        "resolve_fmu_path": resolve_fmu_path,
        "parse_options": parse_options,
        "resolve_fmi_type": resolve_fmi_type,
        "acquire_slot": acquire_slot,
        "submit_simulation": submit_simulation,
        "track_future": track_future,
        "shutdown_executor": shutdown_executor,
        "finalize_tracking": finalize_tracking,
        "save_history": save_history,
        "new_simulation_id": new_simulation_id,
    }


def test_run_router_preserves_local_execution_and_observation_order():
    state = _build_app()
    events = []
    state["observation"].side_effect = lambda *_args, **_kwargs: events.append("observed")
    state["submit_simulation"].side_effect = lambda *args: (events.append("submitted") or ("executor", state["future"]))

    response = state["client"].post("/api/v1/simulations/run", json={
        "labId": "lab-1",
        "parameters": {"mass": 1.5},
        "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.1},
    })

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "simId": "sim-1",
        "simulationTime": 0.25,
        "fmiType": "CoSimulation",
        "time": [0, 1],
        "output": [1.0, 2.0],
    }
    assert events == ["observed", "submitted"]
    state["ensure_local_backend"].assert_called_once_with("Simulation run endpoint")
    state["enforce_reservation"].assert_called_once()
    assert state["enforce_reservation"].call_args.args[1] is None
    state["resolve_fmu_path"].assert_called_once_with("model.fmu")
    state["parse_options"].assert_called_once()
    state["resolve_fmi_type"].assert_called_once_with(None, "/data/model.fmu")
    state["acquire_slot"].assert_called_once_with("lab-1")
    state["track_future"].assert_called_once()
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")
    state["save_history"].assert_awaited_once()


def test_run_router_preserves_station_backend_forwarding_and_gateway_sim_id():
    state = _build_app(mode="station")
    events = []

    class StationBackend:
        def build_authorized_context(self, **kwargs):
            events.append(("context", kwargs))

        async def run_authorized_simulation(self, **kwargs):
            events.append(("run", kwargs))
            return {"status": "completed", "simId": "station-sim", "result": [1]}

    backend = StationBackend()
    state["get_station_backend"].return_value = backend
    state["observation"].side_effect = lambda *_args, **_kwargs: events.append(("observed", None))

    response = state["client"].post(
        "/api/v1/simulations/run",
        headers={"Authorization": "Bearer token"},
        json={"labId": "lab-1", "reservationKey": "res-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed", "simId": "sim-1", "result": [1]}
    assert [event[0] for event in events] == ["context", "observed", "run"]
    state["ensure_local_backend"].assert_not_called()
    state["acquire_slot"].assert_not_called()
    state["request_payload"].assert_called_once()
    state["extract_authorization"].assert_called_once()


def test_run_router_rejects_a_claim_for_another_lab_before_resolving_fmu():
    state = _build_app(claims={
        "labId": "lab-2",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "accessKey": "model.fmu",
        "resourceType": "fmu",
    })

    response = state["client"].post("/api/v1/simulations/run", json={"labId": "lab-1"})

    assert response.status_code == 403
    assert response.json() == {"detail": "JWT not authorised for requested labId"}
    state["resolve_fmu_path"].assert_not_called()
    state["acquire_slot"].assert_not_called()


def test_run_router_preserves_timeout_cleanup():
    pending = Future()
    state = _build_app(future=pending)
    state["parse_options"].return_value = SimpleNamespace(
        start_time=0.0,
        stop_time=1.0,
        step_size=0.1,
        timeout=0.01,
        fmi_type=None,
        solver_name=None,
    )

    response = state["client"].post("/api/v1/simulations/run", json={"labId": "lab-1"})

    assert response.status_code == 504
    assert response.json() == {"detail": "Simulation timed out"}
    assert pending.cancelled()
    state["shutdown_executor"].assert_called_once_with("executor", force=True)
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")


def test_run_router_propagates_observation_failure_without_submitting_work():
    state = _build_app()
    state["observation"].side_effect = HTTPException(status_code=503, detail="observation unavailable")

    response = state["client"].post("/api/v1/simulations/run", json={"labId": "lab-1"})

    assert response.status_code == 503
    assert response.json() == {"detail": "observation unavailable"}
    state["submit_simulation"].assert_not_called()
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")
