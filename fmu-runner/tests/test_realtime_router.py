from fastapi import FastAPI
from fastapi.testclient import TestClient

from realtime_router import create_realtime_router


def _build_app():
    calls = []

    class Manager:
        async def handle_websocket(self, websocket, *, internal):
            calls.append((websocket.url.path, internal))
            await websocket.accept()
            await websocket.send_json({"type": "ready", "internal": internal})
            await websocket.close()

    manager = Manager()
    app = FastAPI()
    app.include_router(create_realtime_router(get_realtime_manager=lambda: manager))
    return TestClient(app), calls


def test_realtime_router_forwards_public_sessions_to_manager():
    client, calls = _build_app()

    with client.websocket_connect("/api/v1/fmu/sessions") as websocket:
        assert websocket.receive_json() == {"type": "ready", "internal": False}

    assert calls == [("/api/v1/fmu/sessions", False)]


def test_realtime_router_forwards_internal_sessions_to_manager():
    client, calls = _build_app()

    with client.websocket_connect("/internal/fmu/sessions") as websocket:
        assert websocket.receive_json() == {"type": "ready", "internal": True}

    assert calls == [("/internal/fmu/sessions", True)]
