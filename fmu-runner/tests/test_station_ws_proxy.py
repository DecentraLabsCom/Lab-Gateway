import asyncio
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from fmu_backend import StationFmuBackend
from station_ws_proxy import StationRealtimeWsProxyManager, _GatewayStationSession


with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": "1", "accessKey": "test.fmu", "resourceType": "fmu"}):
    import main
    from main import app


client = TestClient(app)


def _claims():
    return {
        "sub": "user-1",
        "labId": "1",
        "accessKey": "test.fmu",
        "resourceType": "fmu",
        "nbf": 0,
        "exp": 4102444800,
    }


class _FakeStationConnection:
    def __init__(self):
        self.sent_messages = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, raw_message: str):
        message = json.loads(raw_message)
        self.sent_messages.append(message)
        msg_type = message.get("type")
        if msg_type == "session.create":
            await self._queue.put(json.dumps({
                "type": "session.created",
                "requestId": message["requestId"],
                "sessionId": "sess_station_1",
                "expiresAt": 4102444800,
                "reservationWindow": {"nbf": 0, "exp": 4102444800},
                "capabilities": {"attach": True, "step": True},
            }))
        elif msg_type == "session.attach":
            await self._queue.put(json.dumps({
                "type": "session.attached",
                "requestId": message["requestId"],
                "sessionId": message["sessionId"],
                "state": "created",
            }))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.closed = True
        await self._queue.put(None)


def _build_manager():
    async def _fake_verify(token: str):
        if token != "test-token":
            raise AssertionError("unexpected token")
        return _claims()

    async def _fake_redeem(*, session_ticket: str, lab_id: str | None, reservation_key: str | None, request_id: str | None = None):
        assert session_ticket == "st_valid"
        assert lab_id == "1"
        assert reservation_key == "res-1"
        return _claims()

    return StationRealtimeWsProxyManager(
        logger=main.logger,
        station_backend=StationFmuBackend(
            base_url="https://station.internal/base",
            internal_token="station-secret",
        ),
        verify_jwt_token=_fake_verify,
        enforce_fmu_claim=main._enforce_fmu_claim,
        get_claim_lab_id=main._get_claim_lab_id,
        normalize_lab_id=main._normalize_lab_id,
        coerce_epoch_seconds=main._coerce_epoch_seconds,
        redeem_session_ticket=_fake_redeem,
        ws_cleanup_seconds=60,
        internal_ws_token="gateway-internal",
        ws_create_rate_limit_per_minute=30,
    )


def test_station_ws_session_create_redeems_ticket_and_forwards_context(monkeypatch):
    manager = _build_manager()
    fake_station = _FakeStationConnection()
    captured = {}

    async def _fake_connect(headers):
        captured["headers"] = headers
        return fake_station

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
            "reservationKey": "res-1",
            "sessionTicket": "st_valid",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "session.created"
        assert payload["sessionId"] == "sess_station_1"

    assert captured["headers"]["X-Internal-Session-Token"] == "station-secret"
    assert fake_station.sent_messages[0]["gatewayContext"]["accessKey"] == "test.fmu"
    assert fake_station.sent_messages[0]["gatewayContext"]["reservationKey"] == "res-1"
    assert fake_station.sent_messages[0]["gatewayContext"]["claims"]["sub"] == "user-1"
    assert "sessionTicket" not in fake_station.sent_messages[0]


def test_station_ws_attach_requires_bearer(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess_station_1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "UNAUTHORIZED"


def test_station_ws_attach_forwards_when_session_owned(monkeypatch):
    manager = _build_manager()
    fake_station = _FakeStationConnection()

    async def _fake_connect(_headers):
        return fake_station

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    monkeypatch.setattr(main, "_realtime_manager", manager)
    manager._sessions["sess_station_1"] = _GatewayStationSession(
        session_id="sess_station_1",
        claims=_claims(),
        lab_id="1",
        access_key="test.fmu",
        exp=4102444800,
    )

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess_station_1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "session.attached"
        assert payload["sessionId"] == "sess_station_1"

    assert fake_station.sent_messages[0]["gatewayContext"]["claims"]["accessKey"] == "test.fmu"
