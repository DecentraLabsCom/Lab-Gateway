from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from history_router import create_history_router


def _client():
    claims = {"labId": "lab-1", "accessKey": "model.fmu", "resourceType": "fmu"}

    async def verify_jwt():
        return claims

    enforce_fmu_claim = MagicMock()

    def reject_operation(name):
        raise HTTPException(status_code=501, detail=f"{name} unavailable")

    app = FastAPI()
    app.include_router(create_history_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        reject_unsupported_operation=reject_operation,
    ))
    return TestClient(app), enforce_fmu_claim, claims


def test_history_route_reports_remote_executor_limitation():
    client, enforce_fmu_claim, claims = _client()

    response = client.get("/api/v1/simulations/history?labId=lab-1&limit=5&offset=10")

    assert response.status_code == 501
    assert response.json() == {"detail": "Simulation history endpoint unavailable"}
    enforce_fmu_claim.assert_called_once_with(claims)


def test_result_route_reports_remote_executor_limitation():
    client, enforce_fmu_claim, claims = _client()

    response = client.get("/api/v1/simulations/sim-1/result")

    assert response.status_code == 501
    assert response.json() == {"detail": "Simulation result endpoint unavailable"}
    enforce_fmu_claim.assert_called_once_with(claims)
