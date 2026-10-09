from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from run_router import create_run_router


def _build_app():
    claims = {
        "labId": "lab-1",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "accessKey": "model.fmu",
        "resourceType": "fmu",
    }

    async def verify_jwt():
        return claims

    backend = MagicMock()
    backend.run_authorized_simulation = AsyncMock(
        return_value={"status": "completed", "simId": "executor-sim", "result": [1]},
    )
    enforce_fmu_claim = MagicMock()
    request_payload = MagicMock(return_value={"labId": "lab-1", "simId": "gateway-sim"})
    extract_authorization = MagicMock(return_value="Bearer token")
    observation = AsyncMock(return_value=True)
    new_simulation_id = MagicMock(return_value="gateway-sim")

    app = FastAPI()
    app.include_router(create_run_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        get_station_backend=lambda: backend,
        simulation_request_payload=request_payload,
        extract_authorization_header=extract_authorization,
        record_browser_session_started=observation,
        new_simulation_id=new_simulation_id,
    ))
    return {
        "client": TestClient(app),
        "backend": backend,
        "enforce_fmu_claim": enforce_fmu_claim,
        "request_payload": request_payload,
        "extract_authorization": extract_authorization,
        "observation": observation,
        "new_simulation_id": new_simulation_id,
    }


def test_run_router_forwards_authorized_request_and_returns_gateway_sim_id():
    state = _build_app()
    response = state["client"].post(
        "/api/v1/simulations/run",
        headers={"Authorization": "Bearer token"},
        json={"labId": "lab-1", "reservationKey": "res-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed", "simId": "gateway-sim", "result": [1]}
    state["backend"].build_authorized_context.assert_called_once()
    state["observation"].assert_awaited_once()
    state["backend"].run_authorized_simulation.assert_awaited_once()
    state["request_payload"].assert_called_once()
    state["extract_authorization"].assert_called_once()


def test_run_router_does_not_forward_when_observation_fails():
    state = _build_app()
    state["observation"].side_effect = HTTPException(status_code=503, detail="observation unavailable")

    response = state["client"].post("/api/v1/simulations/run", json={"labId": "lab-1"})

    assert response.status_code == 503
    assert response.json() == {"detail": "observation unavailable"}
    state["backend"].run_authorized_simulation.assert_not_awaited()
