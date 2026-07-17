import pytest
import httpx
from fastapi import HTTPException

from fmu_backend import LocalFmuBackend, StationFmuBackend


@pytest.mark.asyncio
async def test_local_backend_delegates_to_loaders():
    backend = LocalFmuBackend(
        health_loader=lambda: {"status": "UP", "checks": {"fmuDataPath": True}, "fmuCount": 1},
        model_metadata_loader=lambda filename: {"modelName": filename, "modelVariables": []},
        list_loader=lambda access_key: {"fmus": [{"filename": access_key}]},
    )

    health = await backend.health()
    metadata = await backend.get_authorized_model_metadata(
        claims={"accessKey": "demo.fmu"},
        requested_fmu_filename="demo.fmu",
    )
    listing = await backend.list_authorized_fmu(claims={"accessKey": "demo.fmu"})

    assert health["status"] == "UP"
    assert metadata["modelName"] == "demo.fmu"
    assert listing["fmus"][0]["filename"] == "demo.fmu"


@pytest.mark.parametrize(
    "access_key",
    ["../etc/passwd", "provider/../../etc/passwd", "provider\\demo.fmu", "demo.fmu?redirect=1"],
)
def test_fmu_access_key_rejects_path_injection(access_key):
    with pytest.raises(HTTPException) as exc_info:
        StationFmuBackend.ensure_requested_access_key(
            {"accessKey": access_key},
            None,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_station_health_is_degraded_when_not_configured():
    backend = StationFmuBackend(base_url="")

    payload = await backend.health()

    assert payload["status"] == "DEGRADED"
    assert payload["backendMode"] == "station"
    assert payload["checks"]["stationConfigured"] is False
    assert payload["checks"]["stationHealth"] is False


@pytest.mark.asyncio
async def test_station_backend_normalizes_model_metadata(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal")

    async def _fake_request(operation: str, *, access_key: str | None = None):
        assert operation == "describe"
        assert access_key == "demo.fmu"
        return {
            "modelName": "DemoPlant",
            "guid": "demo-guid",
            "fmiVersion": "2.0",
            "simulationType": "CoSimulation",
            "defaultStartTime": 2.5,
            "defaultStopTime": 12.0,
            "defaultStepSize": 0.05,
            "variables": [
                {
                    "name": "u",
                    "type": "Real",
                    "causality": "input",
                    "variability": "continuous",
                    "valueReference": 0,
                    "unit": "V",
                },
                {
                    "name": "y",
                    "type": "Real",
                    "causality": "output",
                    "variability": "continuous",
                    "valueReference": 7,
                },
            ],
        }

    monkeypatch.setattr(backend, "_request_json", _fake_request)

    metadata = await backend.get_authorized_model_metadata(
        claims={"accessKey": "demo.fmu"},
        requested_fmu_filename="demo.fmu",
    )

    assert metadata["modelName"] == "DemoPlant"
    assert metadata["simulationKind"] == "coSimulation"
    assert metadata["simulationType"] == "CoSimulation"
    assert metadata["supportsCoSimulation"] is True
    assert metadata["supportsModelExchange"] is False
    assert metadata["modelVariables"][0]["valueReference"] == 0
    assert metadata["modelVariables"][0]["unit"] == "V"


@pytest.mark.asyncio
async def test_station_catalog_404_falls_back_to_describe(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal")

    async def _fake_request(operation: str, *, access_key: str | None = None):
        if operation == "catalog" and access_key == "demo.fmu":
            raise HTTPException(status_code=404, detail="missing")
        if operation == "describe" and access_key == "demo.fmu":
            return {
                "modelName": "DemoPlant",
                "fmiVersion": "2.0",
                "supportsCoSimulation": True,
                "supportsModelExchange": False,
                "modelVariables": [{"name": "y", "type": "Real", "valueReference": 1}],
            }
        raise AssertionError(f"Unexpected operation: {operation} {access_key}")

    monkeypatch.setattr(backend, "_request_json", _fake_request)

    listing = await backend.list_authorized_fmu(claims={"accessKey": "demo.fmu"})

    assert listing == {
        "fmus": [{
            "filename": "demo.fmu",
            "path": "demo.fmu",
            "source": "station",
            "simulationType": "CoSimulation",
        }]
    }


@pytest.mark.asyncio
async def test_station_catalog_preserves_entries_and_defaults_source(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal")

    async def _fake_request(operation: str, *, access_key: str | None = None):
        assert operation == "catalog"
        assert access_key == "demo.fmu"
        return {
            "fmus": [
                {"filename": "demo.fmu", "path": "provider/demo.fmu"},
                {"filename": "other.fmu", "path": "provider/other.fmu", "source": "station-cache"},
                "ignore-me",
            ]
        }

    monkeypatch.setattr(backend, "_request_json", _fake_request)

    listing = await backend.list_authorized_fmu(claims={"accessKey": "demo.fmu"})

    assert listing == {
        "fmus": [
            {"filename": "demo.fmu", "path": "provider/demo.fmu", "source": "station"},
            {"filename": "other.fmu", "path": "provider/other.fmu", "source": "station-cache"},
        ]
    }


def test_station_backend_derives_internal_session_ws_url():
    backend = StationFmuBackend(base_url="https://station.internal/base")

    assert backend.station_session_ws_url() == "wss://station.internal/base/internal/fmu/sessions"


@pytest.mark.asyncio
async def test_station_backend_forwards_run_request(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal")
    captured: dict = {}

    async def _fake_post(operation: str, *, access_key: str, payload: dict, authorization: str | None = None):
        captured["operation"] = operation
        captured["access_key"] = access_key
        captured["payload"] = payload
        captured["authorization"] = authorization
        return {"status": "completed", "simId": "sim-station-1"}

    monkeypatch.setattr(backend, "_post_json", _fake_post)

    result = await backend.run_authorized_simulation(
        claims={"sub": "user-1", "labId": "1", "accessKey": "demo.fmu"},
        request_payload={
            "labId": "1",
            "reservationKey": "res-1",
            "simId": "sim-gateway-1",
            "parameters": {"u": 1.0},
            "options": {"stopTime": 2.0},
        },
        authorization="Bearer abc",
    )

    assert result["status"] == "completed"
    assert captured["operation"] == "run"
    assert captured["access_key"] == "demo.fmu"
    assert captured["authorization"] == "Bearer abc"
    assert captured["payload"]["claims"]["accessKey"] == "demo.fmu"
    assert captured["payload"]["reservationKey"] == "res-1"
    assert captured["payload"]["simId"] == "sim-gateway-1"


@pytest.mark.asyncio
async def test_station_backend_rejects_untrusted_route_key_before_httpx(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("HTTP client must not be constructed for an invalid key")

    monkeypatch.setattr("fmu_backend.httpx.AsyncClient", UnexpectedClient)

    with pytest.raises(HTTPException) as exc_info:
        await backend._request_json("describe", access_key="../etc/passwd.fmu")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_station_backend_uses_fixed_relative_routes(monkeypatch):
    backend = StationFmuBackend(base_url="https://station.internal/base")
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://station.internal/base"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, path, **kwargs):
            calls.append(("GET", path))
            return httpx.Response(200, json={"status": "UP"})

        async def post(self, path, **kwargs):
            calls.append(("POST", path))
            return httpx.Response(200, json={"status": "completed"})

    monkeypatch.setattr("fmu_backend.httpx.AsyncClient", FakeClient)

    assert await backend._request_json("describe", access_key="provider/demo.fmu") == {"status": "UP"}
    assert await backend._post_json(
        "run", access_key="provider/demo.fmu", payload={}
    ) == {"status": "completed"}
    assert calls == [
        ("GET", "/internal/fmu/describe/provider%2Fdemo.fmu"),
        ("POST", "/internal/fmu/simulations/run/provider%2Fdemo.fmu"),
    ]


def test_station_backend_builds_internal_session_message():
    backend = StationFmuBackend(base_url="https://station.internal")

    message = backend.build_internal_session_message(
        message={"type": "session.create", "requestId": "req-1", "labId": "1"},
        claims={"sub": "user-1", "labId": "1", "accessKey": "demo.fmu", "exp": 4102444800},
        requested_lab_id="1",
        requested_reservation_key="res-1",
    )

    assert message["gatewayContext"]["mode"] == "station"
    assert message["gatewayContext"]["accessKey"] == "demo.fmu"
    assert message["gatewayContext"]["claims"]["sub"] == "user-1"
    assert message["gatewayContext"]["reservationKey"] == "res-1"
