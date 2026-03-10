import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException, WebSocketDisconnect

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


class _AsyncTestWebSocket:
    def __init__(self, messages, *, headers=None, query_params=None, client_host="127.0.0.1", idle_disconnect_after=0.05):
        self._messages = asyncio.Queue()
        for message in messages:
            self._messages.put_nowait(message)
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.client = SimpleNamespace(host=client_host)
        self.sent_json = []
        self.closed_code = None
        self.accepted = False
        self.idle_disconnect_after = idle_disconnect_after

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        waited = 0.0
        while True:
            if self.closed_code is not None:
                raise WebSocketDisconnect()
            try:
                item = self._messages.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)
                waited += 0.01
                if self.idle_disconnect_after is not None and waited >= self.idle_disconnect_after:
                    raise WebSocketDisconnect()
                continue
            if isinstance(item, BaseException):
                raise item
            return item

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def close(self, code=1000):
        self.closed_code = code


class _FailingCloseStationConnection(_FakeStationConnection):
    async def close(self):
        self.closed = True
        raise RuntimeError("close failed")


class _InvalidPayloadStationConnection(_FakeStationConnection):
    async def send(self, raw_message: str):
        message = json.loads(raw_message)
        self.sent_messages.append(message)
        await self._queue.put(b"not-json")


class _ExplodingReaderStationConnection(_FakeStationConnection):
    def __init__(self):
        super().__init__()
        self._raised = False

    async def __anext__(self):
        if self._raised:
            raise RuntimeError("reader exploded")
        self._raised = True
        return await super().__anext__()


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


def _claims_with(**updates):
    claims = _claims()
    claims.update(updates)
    return claims


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


def test_station_proxy_extract_ws_token_supports_query_and_cookie():
    websocket_from_query = SimpleNamespace(headers={}, query_params={"token": "query-token"})
    websocket_from_cookie = SimpleNamespace(headers={"cookie": "foo=bar; jti=cookie-token"}, query_params={})

    assert StationRealtimeWsProxyManager.extract_ws_token(websocket_from_query) == "query-token"
    assert StationRealtimeWsProxyManager.extract_ws_token(websocket_from_cookie) == "cookie-token"


def test_station_proxy_extract_ws_token_requires_credentials():
    websocket = SimpleNamespace(headers={}, query_params={})

    with pytest.raises(HTTPException) as exc:
        StationRealtimeWsProxyManager.extract_ws_token(websocket)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing authentication token"


def test_station_proxy_extract_ws_token_supports_bearer_header():
    websocket = SimpleNamespace(headers={"authorization": "Bearer bearer-token"}, query_params={})

    assert StationRealtimeWsProxyManager.extract_ws_token(websocket) == "bearer-token"


def test_station_proxy_parse_cookie_header_ignores_invalid_chunks():
    cookies = StationRealtimeWsProxyManager.parse_cookie_header("foo=bar; invalid; jwt=abc; spaced = value ")

    assert cookies == {"foo": "bar", "jwt": "abc", "spaced": "value"}


def test_station_proxy_normalize_ticket_id_and_error_payload():
    assert StationRealtimeWsProxyManager._normalize_ticket_id(" st_1234567890abcdef ") == "1234567890"
    assert StationRealtimeWsProxyManager._normalize_ticket_id("   ") is None
    assert StationRealtimeWsProxyManager.error_payload(
        code="FORBIDDEN",
        message="denied",
        request_id="req-1",
        retryable=True,
        session_id="sess-1",
        details={"reason": "lab"},
    ) == {
        "type": "error",
        "code": "FORBIDDEN",
        "message": "denied",
        "retryable": True,
        "requestId": "req-1",
        "sessionId": "sess-1",
        "details": {"reason": "lab"},
    }


def test_station_proxy_rate_limit_discards_stale_hits(monkeypatch):
    manager = _build_manager()
    manager.ws_create_rate_limit_per_minute = 2
    time_values = iter([100.0, 101.0, 161.0])

    monkeypatch.setattr("station_ws_proxy.time.time", lambda: next(time_values))

    assert manager._allow_session_create("sub:user-1") is True
    assert manager._allow_session_create("sub:user-1") is True
    assert manager._allow_session_create("sub:user-1") is True


def test_station_proxy_rate_limit_rejects_when_disabled():
    manager = _build_manager()
    manager.ws_create_rate_limit_per_minute = 0

    assert manager._allow_session_create("sub:user-1") is False


@pytest.mark.asyncio
async def test_station_proxy_cleanup_loop_removes_expired_sessions(monkeypatch):
    manager = _build_manager()
    manager._sessions = {
        "sess-expired": _GatewayStationSession(
            session_id="sess-expired",
            claims=_claims(),
            lab_id="1",
            access_key="test.fmu",
            exp=10,
        ),
        "sess-active": _GatewayStationSession(
            session_id="sess-active",
            claims=_claims(),
            lab_id="1",
            access_key="test.fmu",
            exp=4102444800,
        ),
    }

    sleep_calls = {"count": 0}

    async def _fake_sleep(_seconds):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("station_ws_proxy.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("station_ws_proxy.time.time", lambda: 30)

    with pytest.raises(asyncio.CancelledError):
        await manager._cleanup_loop()

    assert list(manager._sessions.keys()) == ["sess-active"]


@pytest.mark.asyncio
async def test_station_proxy_start_and_stop_manage_cleanup_task():
    manager = _build_manager()
    manager._sessions["sess_station_1"] = _GatewayStationSession(
        session_id="sess_station_1",
        claims=_claims(),
        lab_id="1",
        access_key="test.fmu",
        exp=4102444800,
    )

    await manager.start()
    first_task = manager._cleanup_task
    assert first_task is not None

    await manager.start()
    assert manager._cleanup_task is first_task

    await manager.stop()
    await asyncio.sleep(0)
    assert manager._cleanup_task is None
    assert manager._sessions == {}
    assert first_task.done() is True


@pytest.mark.asyncio
async def test_station_proxy_connect_station_requires_dependency(monkeypatch):
    manager = _build_manager()
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ModuleNotFoundError("missing websockets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    with pytest.raises(HTTPException) as exc:
        await manager._connect_station({"Authorization": "Bearer test-token"})

    assert exc.value.status_code == 500
    assert "websockets dependency" in exc.value.detail


@pytest.mark.asyncio
async def test_station_proxy_connect_station_supports_both_websocket_header_signatures(monkeypatch):
    manager = _build_manager()
    calls = []

    async def _connect_additional(url, additional_headers=None):
        calls.append((url, {"additional_headers": additional_headers}))
        return "connected-additional"

    async def _connect_extra(url, extra_headers=None):
        calls.append((url, {"extra_headers": extra_headers}))
        return "connected-extra"

    module_with_additional = SimpleNamespace(connect=_connect_additional)
    module_with_extra = SimpleNamespace(connect=_connect_extra)

    monkeypatch.setitem(sys.modules, "websockets", module_with_additional)
    connected = await manager._connect_station({"Authorization": "Bearer test-token"})
    assert connected == "connected-additional"
    assert calls[0][1]["additional_headers"]["Authorization"] == "Bearer test-token"

    monkeypatch.setitem(sys.modules, "websockets", module_with_extra)
    connected = await manager._connect_station({"Authorization": "Bearer test-token"})
    assert connected == "connected-extra"
    assert calls[1][1]["extra_headers"]["Authorization"] == "Bearer test-token"

    monkeypatch.delitem(sys.modules, "websockets", raising=False)


def test_station_ws_session_create_requires_ticket_when_unauthenticated(monkeypatch):
    manager = _build_manager()

    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(manager, "verify_jwt_token", _unauthorized)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "UNAUTHORIZED"


def test_station_ws_session_create_requires_redeem_handler_when_ticket_flow_enabled(monkeypatch):
    manager = _build_manager()
    manager.redeem_session_ticket = None

    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(manager, "verify_jwt_token", _unauthorized)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
            "sessionTicket": "st_valid",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INTERNAL_ERROR"


def test_station_ws_session_create_rejects_when_claim_lab_does_not_match(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "2",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "LAB_MISMATCH"


def test_station_ws_session_create_rejects_when_claim_reservation_key_does_not_match(monkeypatch):
    manager = _build_manager()

    async def _verify_with_reservation(_token: str):
        return _claims_with(reservationKey="res-claim")

    monkeypatch.setattr(manager, "verify_jwt_token", _verify_with_reservation)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "reservationKey": "res-other",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_station_ws_session_create_returns_internal_error_when_station_connect_fails(monkeypatch):
    manager = _build_manager()

    async def _fail_connect(_headers):
        raise HTTPException(status_code=503, detail="station unavailable")

    monkeypatch.setattr(manager, "_connect_station", _fail_connect)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INTERNAL_ERROR"
        assert payload["retryable"] is True


def test_station_ws_attach_rejects_expired_session(monkeypatch):
    manager = _build_manager()
    manager._sessions["sess_station_1"] = _GatewayStationSession(
        session_id="sess_station_1",
        claims=_claims(),
        lab_id="1",
        access_key="test.fmu",
        exp=1,
    )
    monkeypatch.setattr(main, "_realtime_manager", manager)
    monkeypatch.setattr("station_ws_proxy.time.time", lambda: 100)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess_station_1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "SESSION_EXPIRED"

    assert "sess_station_1" not in manager._sessions


def test_station_ws_attach_rejects_session_ownership_mismatch(monkeypatch):
    manager = _build_manager()
    manager._sessions["sess_station_1"] = _GatewayStationSession(
        session_id="sess_station_1",
        claims=_claims(),
        lab_id="1",
        access_key="test.fmu",
        exp=4102444800,
    )

    async def _verify_other(_token: str):
        return _claims_with(sub="user-2")

    monkeypatch.setattr(manager, "verify_jwt_token", _verify_other)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess_station_1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_station_ws_attach_requires_session_id(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_station_ws_attach_rejects_unknown_session(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess-missing",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_station_ws_attach_returns_internal_error_when_station_connect_fails(monkeypatch):
    manager = _build_manager()
    manager._sessions["sess_station_1"] = _GatewayStationSession(
        session_id="sess_station_1",
        claims=_claims(),
        lab_id="1",
        access_key="test.fmu",
        exp=4102444800,
    )

    async def _fail_connect(_headers):
        raise HTTPException(status_code=503, detail="station unavailable")

    monkeypatch.setattr(manager, "_connect_station", _fail_connect)
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess_station_1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INTERNAL_ERROR"
        assert payload["retryable"] is True


def test_station_ws_internal_endpoint_rejects_invalid_internal_token(monkeypatch):
    manager = _build_manager()
    monkeypatch.setattr(main, "_realtime_manager", manager)

    with client.websocket_connect("/internal/fmu/sessions?token=test-token", headers={"X-Internal-Session-Token": "wrong-token"}) as ws:
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_validates_basic_message_shape():
    manager = _build_manager()
    websocket = _AsyncTestWebSocket(
        messages=[
            "{invalid-json",
            json.dumps({"requestId": "req-no-type"}),
            json.dumps({"type": "session.create"}),
            json.dumps({"type": "sim.step", "requestId": "req-step"}),
            WebSocketDisconnect(),
        ],
        headers={"authorization": "Bearer test-token"},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert websocket.accepted is True
    assert [payload["message"] for payload in websocket.sent_json] == [
        "Invalid JSON payload",
        "Missing message type",
        "Missing requestId",
        "Create or attach a session first",
    ]


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_caches_error_responses_for_duplicate_request_ids(monkeypatch):
    manager = _build_manager()

    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(manager, "verify_jwt_token", _unauthorized)
    websocket = _AsyncTestWebSocket(
        messages=[
            json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}),
            json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}),
        ],
        headers={},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert len(websocket.sent_json) == 2
    assert websocket.sent_json[0] == websocket.sent_json[1]
    assert websocket.sent_json[0]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_reader_maps_invalid_station_payload(monkeypatch):
    manager = _build_manager()
    fake_station = _InvalidPayloadStationConnection()

    async def _fake_connect(_headers):
        return fake_station

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    websocket = _AsyncTestWebSocket(
        messages=[
            json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}),
        ],
        headers={"authorization": "Bearer test-token"},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert websocket.sent_json[0]["code"] == "INTERNAL_ERROR"
    assert websocket.sent_json[0]["message"] == "Station backend returned invalid websocket payload"
    assert fake_station.closed is True


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_reader_cleans_closed_sessions(monkeypatch):
    manager = _build_manager()
    fake_station = _FakeStationConnection()

    async def _fake_connect(_headers):
        return fake_station

    async def _send_with_close(raw_message: str):
        await _FakeStationConnection.send(fake_station, raw_message)
        await fake_station._queue.put(json.dumps({
            "type": "session.closed",
            "requestId": "req-close",
            "sessionId": "sess_station_1",
        }))

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    monkeypatch.setattr(fake_station, "send", _send_with_close)
    websocket = _AsyncTestWebSocket(
        messages=[
            json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}),
        ],
        headers={"authorization": "Bearer test-token"},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert [payload["type"] for payload in websocket.sent_json[:2]] == ["session.created", "session.closed"]
    assert "sess_station_1" not in manager._sessions


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_reader_reports_unexpected_station_failure(monkeypatch):
    manager = _build_manager()
    fake_station = _ExplodingReaderStationConnection()
    await fake_station._queue.put(json.dumps({
        "type": "session.created",
        "requestId": "req-create",
        "sessionId": "sess_station_1",
        "expiresAt": 4102444800,
    }))

    async def _fake_connect(_headers):
        return fake_station

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    websocket = _AsyncTestWebSocket(
        messages=[json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"})],
        headers={"authorization": "Bearer test-token"},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert websocket.closed_code == 1011
    assert websocket.sent_json[0]["type"] == "session.created"
    assert websocket.sent_json[1]["code"] == "INTERNAL_ERROR"
    assert websocket.sent_json[1]["message"] == "Station realtime session channel closed unexpectedly"
    assert fake_station.closed is True


@pytest.mark.asyncio
async def test_station_proxy_handle_websocket_tolerates_station_close_errors(monkeypatch):
    manager = _build_manager()
    fake_station = _FailingCloseStationConnection()

    async def _fake_connect(_headers):
        return fake_station

    monkeypatch.setattr(manager, "_connect_station", _fake_connect)
    websocket = _AsyncTestWebSocket(
        messages=[
            json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}),
            WebSocketDisconnect(),
        ],
        headers={"authorization": "Bearer test-token"},
    )

    await manager.handle_websocket(websocket, internal=False)

    assert fake_station.sent_messages[0]["type"] == "session.create"
