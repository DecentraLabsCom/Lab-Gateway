from unittest.mock import patch

from fastapi.testclient import TestClient


with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": "1", "accessKey": "test.fmu", "resourceType": "fmu"}):
    import main
    from main import app
    from auth import verify_jwt as _original_verify_jwt


def _fake_jwt(**claims):
    merged = {"sub": "test-user", "labId": "1", "accessKey": "test.fmu", "resourceType": "fmu"}
    merged.update(claims)
    merged = {k: v for k, v in merged.items() if v is not None}

    async def _override():
        return merged

    return _override


app.dependency_overrides[_original_verify_jwt] = _fake_jwt()
client = TestClient(app)


class _StationBackendStub:
    async def run_authorized_simulation(self, *, claims, request_payload, authorization=None):
        self.run_call = {
            "claims": claims,
            "request_payload": request_payload,
            "authorization": authorization,
        }
        return {"status": "completed", "simId": "sim-station-1"}

    async def open_authorized_simulation_stream(self, *, claims, request_payload, authorization=None):
        self.stream_call = {
            "claims": claims,
            "request_payload": request_payload,
            "authorization": authorization,
        }

        class _Client:
            def __init__(self):
                self.closed = False

            async def aclose(self):
                self.closed = True

        class _Response:
            status_code = 200
            headers = {"content-type": "application/x-ndjson"}

            def __init__(self):
                self.closed = False

            async def aiter_bytes(self):
                yield b'{"type":"started"}\n'
                yield b'{"type":"completed"}\n'

            async def aclose(self):
                self.closed = True

        return _Client(), _Response()


def test_run_station_mode_forwards_request(monkeypatch):
    station_backend = _StationBackendStub()
    monkeypatch.setattr(main, "_fmu_backend", type("StationMode", (), {"mode": "station"})())
    monkeypatch.setattr(main, "_get_station_backend", lambda: station_backend)

    response = client.post(
        "/api/v1/simulations/run",
        json={
            "labId": "1",
            "reservationKey": "res-1",
            "parameters": {"u": 1.0},
            "options": {"stopTime": 2.0},
        },
        headers={"Authorization": "Bearer station-token"},
    )

    assert response.status_code == 200
    assert response.json()["simId"] == "sim-station-1"
    assert station_backend.run_call["authorization"] == "Bearer station-token"
    assert station_backend.run_call["request_payload"]["reservationKey"] == "res-1"


def test_stream_station_mode_forwards_request(monkeypatch):
    station_backend = _StationBackendStub()
    monkeypatch.setattr(main, "_fmu_backend", type("StationMode", (), {"mode": "station"})())
    monkeypatch.setattr(main, "_get_station_backend", lambda: station_backend)

    response = client.post(
        "/api/v1/simulations/stream",
        json={
            "labId": "1",
            "reservationKey": "res-1",
            "parameters": {"u": 1.0},
            "options": {"stopTime": 2.0},
        },
        headers={"Authorization": "Bearer station-token"},
    )

    assert response.status_code == 200
    assert response.text == '{"type":"started"}\n{"type":"completed"}\n'
    assert station_backend.stream_call["authorization"] == "Bearer station-token"
    assert station_backend.stream_call["request_payload"]["labId"] == "1"


def test_history_is_blocked_in_station_mode(monkeypatch):
    monkeypatch.setattr(main, "_fmu_backend", type("StationMode", (), {"mode": "station", "supports_local_execution": False})())

    response = client.get("/api/v1/simulations/history")

    assert response.status_code == 501
    assert "FMU_BACKEND_MODE=station" in response.json()["detail"]
