from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from stream_router import create_stream_router


def test_stream_router_forwards_the_request_to_remote_executor():
    claims = {
        "labId": "lab-1",
        "reservationKey": "res-1",
        "pucHash": "puc-1",
        "accessKey": "model.fmu",
        "resourceType": "fmu",
    }

    async def verify_jwt():
        return claims

    stream = AsyncMock(return_value=StreamingResponse(
        iter([b'{"type":"started"}\n']),
        media_type="application/x-ndjson",
    ))
    enforce_fmu_claim = MagicMock()
    app = FastAPI()
    app.include_router(create_stream_router(
        verify_jwt=verify_jwt,
        enforce_fmu_claim=enforce_fmu_claim,
        stream_station_simulation=stream,
    ))

    response = TestClient(app).post(
        "/api/v1/simulations/stream",
        headers={"Authorization": "Bearer token"},
        json={"labId": "lab-1", "reservationKey": "res-1"},
    )

    assert response.status_code == 200
    assert response.text == '{"type":"started"}\n'
    stream.assert_awaited_once()
    enforce_fmu_claim.assert_called_once_with(claims)
