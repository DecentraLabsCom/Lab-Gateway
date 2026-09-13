import json
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from stream_router import create_stream_router
from simulation_stream_payloads import build_completed_event, iter_result_chunks
from stream_errors import build_stream_error_payload


def _build_app(*, mode="local", claims=None, future=None, execution_options=None, clock_values=None):
    resolved_claims = claims or {
        "labId": "lab-1",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "accessKey": "model.fmu",
        "resourceType": "fmu",
    }
    local_future = future or Future()
    if future is None:
        local_future.set_result({
            "time": [0, 1],
            "outputs": {"y": [1.0, 2.0]},
            "outputVariables": ["y"],
        })

    async def verify_jwt():
        return resolved_claims

    enforce_fmu_claim = MagicMock()
    ensure_local_backend = MagicMock()
    station_stream = AsyncMock()
    get_claim_lab_id = MagicMock(side_effect=lambda current_claims: current_claims.get("labId"))
    normalize_lab_id = MagicMock(side_effect=lambda value: str(value).strip() if value else None)
    enforce_reservation = MagicMock()
    resolve_fmu_path = MagicMock(return_value="/data/model.fmu")
    resolved_options = execution_options or SimpleNamespace(
        start_time=0.0,
        stop_time=1.0,
        step_size=0.1,
        timeout=2.0,
        fmi_type=None,
        solver_name=None,
    )
    parse_options = MagicMock(return_value=resolved_options)
    resolve_fmi_type = MagicMock(return_value="CoSimulation")
    new_simulation_id = MagicMock(return_value="sim-1")
    monotonic = MagicMock(side_effect=clock_values or [100.0, 100.25])
    acquire_slot = MagicMock()
    observation = AsyncMock(return_value=True)
    submit_simulation = MagicMock(return_value=("executor", local_future))
    track_future = MagicMock()
    shutdown_executor = MagicMock()
    finalize_tracking = MagicMock()
    save_history = AsyncMock()
    logger = MagicMock()

    async def sleep(_seconds):
        return None

    app = FastAPI()
    app.include_router(create_stream_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        get_backend_mode=lambda: mode,
        stream_station_simulation=station_stream,
        ensure_local_execution_backend=ensure_local_backend,
        get_claim_lab_id=get_claim_lab_id,
        normalize_lab_id=normalize_lab_id,
        enforce_requested_reservation=enforce_reservation,
        resolve_fmu_path=resolve_fmu_path,
        parse_simulation_options=parse_options,
        resolve_fmi_type=resolve_fmi_type,
        new_simulation_id=new_simulation_id,
        monotonic=monotonic,
        acquire_slot=acquire_slot,
        record_browser_session_started=observation,
        submit_simulation=submit_simulation,
        track_running_future=track_future,
        shutdown_executor=shutdown_executor,
        finalize_tracking=finalize_tracking,
        iter_result_chunks=iter_result_chunks,
        build_completed_event=build_completed_event,
        stream_error_payload=build_stream_error_payload,
        save_history=save_history,
        sleep=sleep,
        logger=logger,
    ))
    return {
        "client": TestClient(app),
        "future": local_future,
        "observation": observation,
        "submit_simulation": submit_simulation,
        "shutdown_executor": shutdown_executor,
        "finalize_tracking": finalize_tracking,
        "resolve_fmu_path": resolve_fmu_path,
        "acquire_slot": acquire_slot,
        "station_stream": station_stream,
    }


def _events(response):
    return [json.loads(line) for line in response.text.strip().splitlines() if line.strip()]


def test_stream_router_preserves_local_ndjson_order_and_cleanup():
    state = _build_app()
    events = []
    state["observation"].side_effect = lambda *_args, **_kwargs: events.append("observed")
    state["submit_simulation"].side_effect = lambda *args: (events.append("submitted") or ("executor", state["future"]))

    response = state["client"].post("/api/v1/simulations/stream", json={"labId": "lab-1"})

    assert response.status_code == 200
    assert "application/x-ndjson" in response.headers["content-type"]
    payloads = _events(response)
    assert [event["type"] for event in payloads] == ["started", "data", "data", "completed"]
    assert payloads[0] == {"type": "started", "simId": "sim-1"}
    assert payloads[-1] == {
        "type": "completed",
        "simId": "sim-1",
        "simulationTime": 0.25,
        "fmiType": "CoSimulation",
        "outputVariables": ["y"],
    }
    assert events == ["observed", "submitted"]
    state["acquire_slot"].assert_called_once_with("lab-1")
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")


def test_stream_router_preserves_station_forwarding_contract():
    state = _build_app(mode="station")

    async def station_stream(request, req, claims):
        assert req.labId == "lab-1"
        assert claims["reservationKey"] == "res-1"
        assert request.headers.get("Authorization") == "Bearer token"
        return StreamingResponse(iter([b'{"type":"started"}\n']), media_type="application/x-ndjson")

    state["station_stream"].side_effect = station_stream
    response = state["client"].post(
        "/api/v1/simulations/stream",
        headers={"Authorization": "Bearer token"},
        json={"labId": "lab-1", "reservationKey": "res-1"},
    )

    assert response.status_code == 200
    assert response.text == '{"type":"started"}\n'
    state["observation"].assert_not_awaited()
    state["submit_simulation"].assert_not_called()


def test_stream_router_emits_safe_observation_error_without_submitting():
    state = _build_app()
    state["observation"].side_effect = HTTPException(
        status_code=503,
        detail={"code": "SESSION_OBSERVATION_UNAVAILABLE", "error": "audit unavailable"},
    )

    response = state["client"].post("/api/v1/simulations/stream", json={"labId": "lab-1"})

    assert response.status_code == 200
    assert _events(response) == [{
        "type": "error",
        "simId": "sim-1",
        "code": "SESSION_OBSERVATION_UNAVAILABLE",
        "detail": "audit unavailable",
    }]
    state["submit_simulation"].assert_not_called()
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")


def test_stream_router_preserves_timeout_event_and_forced_cleanup():
    pending = Future()
    state = _build_app(
        future=pending,
        execution_options=SimpleNamespace(
            start_time=0.0,
            stop_time=1.0,
            step_size=0.1,
            timeout=0.5,
            fmi_type=None,
            solver_name=None,
        ),
        clock_values=[100.0, 100.6],
    )
    state["future"].cancel = MagicMock(side_effect=state["future"].cancel)

    response = state["client"].post("/api/v1/simulations/stream", json={"labId": "lab-1"})

    assert response.status_code == 200
    payloads = _events(response)
    assert payloads == [
        {"type": "started", "simId": "sim-1"},
        {"type": "error", "simId": "sim-1", "detail": "Simulation timed out"},
    ]
    state["future"].cancel.assert_called_once_with()
    state["shutdown_executor"].assert_called_once_with("executor", force=True)
    state["finalize_tracking"].assert_called_once_with("sim-1", "lab-1")


def test_stream_router_rejects_a_claim_for_another_lab_before_resolving_fmu():
    state = _build_app(claims={"labId": "lab-2", "accessKey": "model.fmu", "resourceType": "fmu"})

    response = state["client"].post("/api/v1/simulations/stream", json={"labId": "lab-1"})

    assert response.status_code == 403
    assert response.json() == {"detail": "JWT not authorised for requested labId"}
    state["resolve_fmu_path"].assert_not_called()
