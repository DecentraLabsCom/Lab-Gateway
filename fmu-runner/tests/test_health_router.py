from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from health_router import create_health_router


def _client(*, backend_payload, auth_status):
    refresh_jwks = AsyncMock()
    backend_health = AsyncMock(return_value=backend_payload)
    auth_health = lambda: auth_status
    app = FastAPI()
    app.include_router(create_health_router(
        backend_health=backend_health,
        refresh_jwks=refresh_jwks,
        auth_health=auth_health,
    ))
    return TestClient(app), backend_health, refresh_jwks


def test_health_router_reports_up_and_refreshes_jwks():
    client, backend_health, refresh_jwks = _client(
        backend_payload={"status": "UP", "checks": {"backend": True}},
        auth_status={"status": "UP", "stale": False, "cachedKeys": 1},
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "UP",
        "checks": {"backend": True, "jwks": True},
        "auth": {"status": "UP", "stale": False, "cachedKeys": 1},
    }
    backend_health.assert_awaited_once_with()
    refresh_jwks.assert_awaited_once_with()


def test_health_router_reports_degraded_when_jwks_is_degraded():
    client, _, _ = _client(
        backend_payload={"status": "UP", "checks": {}},
        auth_status={"status": "DEGRADED", "stale": True, "cachedKeys": 1},
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"
    assert response.json()["checks"]["jwks"] is False


def test_health_router_reports_down_when_jwks_is_down():
    client, _, refresh_jwks = _client(
        backend_payload={"status": "UP", "checks": {"backend": True}},
        auth_status={"status": "DOWN", "stale": False, "cachedKeys": 0},
    )
    refresh_jwks.side_effect = HTTPException(status_code=503, detail="issuer unavailable")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "DOWN"
    assert response.json()["checks"]["jwks"] is False