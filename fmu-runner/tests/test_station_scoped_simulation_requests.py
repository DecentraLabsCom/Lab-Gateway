"""History, results and cancellation must carry the same reservation scope."""

import base64
import json

from fastapi import HTTPException
import httpx
import pytest

from fmu_backend import StationFmuBackend
import fmu_backend


CLAIMS = {"sub": "consumer", "labId": "42", "accessKey": "provider/model.fmu",
          "reservationKey": "reservation-1", "pucHash": "puc-1", "resourceType": "fmu", "exp": 4102444800}


def _transport(monkeypatch, response=None, error=None):
    calls = []

    class Client:
        def __init__(self, **options):
            assert options["base_url"] == "https://station.internal"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if error is not None:
                raise error
            return response or httpx.Response(200, json={"status": "completed"})

    monkeypatch.setattr(fmu_backend.httpx, "AsyncClient", Client)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,method,path,params", [
    ("history", "GET", "/internal/fmu/simulations/history", {"limit": 7, "offset": 2}),
    ("status", "GET", "/internal/fmu/simulations/sim-1", None),
    ("result", "GET", "/internal/fmu/simulations/sim-1/result", None),
    ("cancel", "POST", "/internal/fmu/simulations/sim-1/cancel", None),
])
async def test_every_simulation_operation_carries_authenticated_gateway_scope(monkeypatch, operation, method, path, params):
    calls = _transport(monkeypatch)
    backend = StationFmuBackend(base_url="https://station.internal", internal_token="station-token")
    if operation == "history":
        result = await backend.get_authorized_simulation_history(claims=CLAIMS, limit=7, offset=2, requested_lab_id="42")
    elif operation == "cancel":
        result = await backend.cancel_authorized_simulation(claims=CLAIMS, sim_id="sim-1")
    else:
        result = await getattr(backend, "get_authorized_simulation_" + operation)(claims=CLAIMS, sim_id="sim-1")
    assert result == {"status": "completed"}
    assert len(calls) == 1
    actual_method, actual_path, request = calls[0]
    assert (actual_method, actual_path, request["params"]) == (method, path, params)
    encoded = request["headers"]["X-Gateway-Context"]
    context = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert context["labId"] == "42"
    assert context["reservationKey"] == "reservation-1"
    assert context["accessKey"] == "provider/model.fmu"
    assert context["claims"]["sub"] == "consumer"


@pytest.mark.asyncio
@pytest.mark.parametrize("response,error,status", [
    (httpx.Response(403, json={"detail": "not authorized"}), None, 403),
    (httpx.Response(404, json={"detail": "missing"}), None, 404),
    (httpx.Response(200, content=b"not JSON"), None, 502),
    (httpx.Response(200, json=[]), None, 502),
    (None, httpx.ConnectError("private station details"), 503),
])
async def test_scoped_operations_reject_invalid_station_responses_without_leaking_errors(monkeypatch, response, error, status):
    calls = _transport(monkeypatch, response, error)
    backend = StationFmuBackend(base_url="https://station.internal")
    with pytest.raises(HTTPException) as failure:
        await backend.get_authorized_simulation_status(claims=CLAIMS, sim_id="sim-1")
    assert failure.value.status_code == status
    assert "private station details" not in str(failure.value.detail)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("sim_id", ["", "../escape", "has spaces"])
async def test_invalid_simulation_ids_never_reach_the_station(monkeypatch, sim_id):
    calls = _transport(monkeypatch)
    with pytest.raises(HTTPException) as failure:
        await StationFmuBackend(base_url="https://station.internal").get_authorized_simulation_result(claims=CLAIMS, sim_id=sim_id)
    assert failure.value.status_code == 400
    assert calls == []


@pytest.mark.asyncio
async def test_missing_station_and_oversized_gateway_context_fail_before_network_io(monkeypatch):
    calls = _transport(monkeypatch)
    with pytest.raises(HTTPException) as missing:
        await StationFmuBackend(base_url="").get_authorized_simulation_history(claims=CLAIMS)
    assert missing.value.status_code == 503
    with pytest.raises(HTTPException) as oversized:
        await StationFmuBackend(base_url="https://station.internal").get_authorized_simulation_status(
            claims={**CLAIMS, "sub": "x" * 12000}, sim_id="sim-1")
    assert oversized.value.status_code == 413
    assert calls == []
