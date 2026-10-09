from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from cancel_router import create_cancel_router


def test_cancel_router_keeps_authentication_and_reports_unsupported_operation():
    claims = {"labId": "lab-1", "accessKey": "model.fmu", "resourceType": "fmu"}

    async def verify_jwt():
        return claims

    enforce_fmu_claim = MagicMock()

    def reject_operation(name):
        assert name == "Simulation cancel endpoint"
        raise HTTPException(status_code=501, detail="remote cancellation is unsupported")

    app = FastAPI()
    app.include_router(create_cancel_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        reject_unsupported_operation=reject_operation,
    ))

    response = TestClient(app).post("/api/v1/simulations/sim-1/cancel")

    assert response.status_code == 501
    assert response.json() == {"detail": "remote cancellation is unsupported"}
    enforce_fmu_claim.assert_called_once_with(claims)
