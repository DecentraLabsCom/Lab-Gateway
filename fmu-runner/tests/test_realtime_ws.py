import json
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from realtime_ws import RealtimeWsManager, _RealtimeSession, _StreamSubscription, _WsConnection


with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": "1", "accessKey": "test.fmu", "resourceType": "fmu"}):
    from main import app, _realtime_manager


client = TestClient(app)


def _claims():
    return {
        "sub": "user-1",
        "labId": "1",
        "accessKey": "test.fmu",
        "resourceType": "fmu",
        "nbf": 0,
        "exp": 4102444800,  # 2100-01-01
    }


def _build_session(manager=None, claims=None):
    return _RealtimeSession(manager or _realtime_manager, "sess-unit", claims or _claims(), Path("/tmp/test.fmu"))


def _build_manager():
    return RealtimeWsManager(
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
        verify_jwt_token=None,
        enforce_fmu_claim=lambda claims: None,
        resolve_fmu_path=lambda access_key: Path(f"/tmp/{access_key}"),
        get_claim_lab_id=lambda claims: str(claims.get("labId")) if claims.get("labId") is not None else None,
        normalize_lab_id=lambda value: str(value) if value is not None else None,
        coerce_epoch_seconds=lambda value: int(value) if value is not None else None,
        acquire_slot=lambda lab_id: None,
        release_slot=lambda lab_id: None,
    )


def _claims_with(**updates):
    claims = _claims()
    claims.update(updates)
    return claims


def _create_ws_session(ws, request_id="req-create", lab_id="1"):
    ws.send_text(json.dumps({"type": "session.create", "requestId": request_id, "labId": lab_id}))
    created = ws.receive_json()
    assert created["type"] == "session.created"
    return created


def _mock_model_description():
    class _Var:
        def __init__(self, name, vtype, causality="output", variability="continuous", start=None, unit=None):
            self.name = name
            self.type = vtype
            self.causality = causality
            self.variability = variability
            self.start = start
            self.unit = unit
            self.valueReference = 1

    class _MD:
        fmiVersion = "2.0"
        coSimulation = True
        modelExchange = False
        modelVariables = [
            _Var("u1", "Real", causality="input", start=0.0, unit="V"),
            _Var("y", "Real", causality="output", unit="V"),
        ]

    return _MD()


def _mock_model_description_fmi3():
    class _Var:
        def __init__(self, name, vtype, causality="output", variability="continuous", start=None, unit=None):
            self.name = name
            self.type = vtype
            self.causality = causality
            self.variability = variability
            self.start = start
            self.unit = unit
            self.valueReference = 1
            self.dimensions = []

    class _MD:
        fmiVersion = "3.0"
        coSimulation = True
        modelExchange = False
        modelVariables = [
            _Var("u1", "Float64", causality="input", start=0.0, unit="V"),
            _Var("y", "Float64", causality="output", unit="V"),
        ]

    return _MD()


def _mock_model_description_fmi3_array():
    class _Dimension:
        def __init__(self, value_reference):
            self.valueReference = value_reference
            self.start = None
            self.variable = None

    class _Var:
        def __init__(self, name, value_reference, vtype, causality="output", variability="continuous", start=None, dimensions=None):
            self.name = name
            self.type = vtype
            self.causality = causality
            self.variability = variability
            self.start = start
            self.unit = None
            self.valueReference = value_reference
            self.dimensions = dimensions or []

    class _MD:
        fmiVersion = "3.0"
        coSimulation = True
        modelExchange = False
        modelVariables = [
            _Var("m", 1, "UInt64", causality="structuralParameter", variability="fixed", start=3),
            _Var("u", 9, "Float64", causality="input", dimensions=[_Dimension(1)]),
            _Var("y", 10, "Float64", causality="output", dimensions=[_Dimension(1)]),
        ]

    return _MD()


@pytest.fixture(autouse=True)
def _patch_realtime_manager(monkeypatch):
    async def _fake_verify(_token: str):
        return _claims()

    async def _fake_redeem(*, session_ticket: str, lab_id: str | None, reservation_key: str | None, request_id: str | None = None):
        if session_ticket != "st_valid":
            raise RuntimeError("invalid ticket")
        return _claims()

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _fake_verify)
    monkeypatch.setattr(_realtime_manager, "redeem_session_ticket", _fake_redeem)
    monkeypatch.setattr(_realtime_manager, "resolve_fmu_path", lambda _name: Path("/tmp/test.fmu"))
    monkeypatch.setattr(_realtime_manager, "acquire_slot", lambda _lab_id: None)
    monkeypatch.setattr(_realtime_manager, "release_slot", lambda _lab_id: None)
    yield
    _realtime_manager._sessions.clear()


def test_ws_requires_request_id():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "labId": "1"}))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"
        assert "requestId" in payload["message"]


def test_ws_rejects_invalid_json_payload():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text("{not-json")
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_ws_requires_message_type():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"requestId": "req-type"}))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"
        assert "message type" in payload["message"]


def test_ws_create_and_model_describe():
    with patch("realtime_ws.read_model_description", return_value=_mock_model_description()):
        with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
            ws.send_text(json.dumps({"type": "session.create", "requestId": "req-1", "labId": "1"}))
            created = ws.receive_json()
            assert created["type"] == "session.created"
            assert created["requestId"] == "req-1"
            assert created["sessionId"].startswith("sess_")
            assert created["reservationWindow"]["exp"] == _claims()["exp"]

            ws.send_text(json.dumps({"type": "model.describe", "requestId": "req-2", "sessionId": created["sessionId"]}))
            described = ws.receive_json()
            assert described["type"] == "model.description"
            assert described["requestId"] == "req-2"
            assert described["fmiVersion"] == "2.0"
            assert described["simulationKind"] == "coSimulation"
            assert any(v["name"] == "u1" for v in described["variables"])


def test_ws_attach_and_terminate_idempotent():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws1:
        ws1.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws1.receive_json()
        session_id = created["sessionId"]

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws2:
        ws2.send_text(json.dumps({"type": "session.attach", "requestId": "req-attach", "sessionId": session_id}))
        attached = ws2.receive_json()
        assert attached["type"] == "session.attached"
        assert attached["sessionId"] == session_id

        ws2.send_text(json.dumps({"type": "session.terminate", "requestId": "req-term", "sessionId": session_id}))
        closed_1 = ws2.receive_json()
        assert closed_1["type"] == "session.closed"

        ws2.send_text(json.dumps({"type": "session.terminate", "requestId": "req-term", "sessionId": session_id}))
        closed_2 = ws2.receive_json()
        assert closed_2 == closed_1


def test_ws_create_with_session_ticket_without_bearer():
    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-ticket",
            "labId": "1",
            "reservationKey": "0xabc",
            "sessionTicket": "st_valid",
        }))
        created = ws.receive_json()
        assert created["type"] == "session.created"
        assert created["sessionId"].startswith("sess_")


def test_ws_create_is_rate_limited(monkeypatch):
    monkeypatch.setattr(_realtime_manager, "ws_create_rate_limit_per_minute", 0)
    _realtime_manager._create_hits.clear()
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-limit", "labId": "1"}))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_ws_internal_endpoint_rejects_invalid_internal_token():
    manager = _build_manager()
    manager.internal_ws_token = "expected-token"

    async def _fake_verify(_token: str):
        return _claims()

    manager.verify_jwt_token = _fake_verify

    class _WebSocket:
        def __init__(self):
            self.headers = {"x-internal-session-token": "wrong-token", "authorization": "Bearer test-token"}
            self.query_params = {}
            self.client = SimpleNamespace(host="127.0.0.1")
            self.sent = []
            self.close_calls = []
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code=None):
            self.close_calls.append(code)

        async def receive_text(self):
            raise AssertionError("receive_text should not be called when internal auth fails")

    websocket = _WebSocket()

    await manager.handle_websocket(websocket, internal=True)

    assert websocket.accepted is True
    assert websocket.sent[0]["type"] == "error"
    assert websocket.sent[0]["code"] == "FORBIDDEN"
    assert 1008 in websocket.close_calls


def test_ws_session_create_requires_ticket_when_unauthenticated(monkeypatch):
    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _unauthorized)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "UNAUTHORIZED"


def test_ws_session_create_requires_redeem_handler_when_ticket_mode_is_used(monkeypatch):
    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _unauthorized)
    monkeypatch.setattr(_realtime_manager, "redeem_session_ticket", None)

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


def test_ws_session_create_rejects_lab_mismatch(monkeypatch):
    async def _mismatch_verify(_token: str):
        return _claims_with(labId="2")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _mismatch_verify)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "LAB_MISMATCH"


def test_ws_session_create_rejects_missing_authorized_fmu(monkeypatch):
    async def _no_access_key(_token: str):
        return _claims_with(accessKey=None)

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _no_access_key)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_ws_session_create_rejects_expired_reservation(monkeypatch):
    async def _expired_verify(_token: str):
        return _claims_with(exp=1)

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _expired_verify)
    monkeypatch.setattr("realtime_ws.time.time", lambda: 100)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.create",
            "requestId": "req-create",
            "labId": "1",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "SESSION_EXPIRED"


def test_ws_session_attach_rejects_missing_session():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "missing-session",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_ws_session_attach_rejects_ownership_mismatch(monkeypatch):
    async def _other_verify(_token: str):
        return _claims_with(sub="user-2")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _other_verify)
    _realtime_manager._sessions["sess-owned"] = _build_session(claims=_claims())
    _realtime_manager._sessions["sess-owned"].session_id = "sess-owned"

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({
            "type": "session.attach",
            "requestId": "req-attach",
            "sessionId": "sess-owned",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_ws_session_ping_returns_pong():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws.receive_json()

        ws.send_text(json.dumps({"type": "session.ping", "requestId": "req-ping", "sessionId": created["sessionId"]}))
        payload = ws.receive_json()
        assert payload["type"] == "session.pong"
        assert payload["sessionId"] == created["sessionId"]


def test_ws_sim_set_inputs_requires_object_values():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws.receive_json()

        ws.send_text(json.dumps({
            "type": "sim.setInputs",
            "requestId": "req-inputs",
            "sessionId": created["sessionId"],
            "values": ["not-an-object"],
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_ws_sim_get_outputs_requires_variables_array():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws.receive_json()

        ws.send_text(json.dumps({
            "type": "sim.getOutputs",
            "requestId": "req-outputs",
            "sessionId": created["sessionId"],
            "variables": "y",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_ws_sim_subscribe_outputs_requires_variables_array():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws.receive_json()

        ws.send_text(json.dumps({
            "type": "sim.subscribeOutputs",
            "requestId": "req-subscribe",
            "sessionId": created["sessionId"],
            "variables": "y",
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_ws_rejects_unsupported_command_after_session_create():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        created = ws.receive_json()

        ws.send_text(json.dumps({
            "type": "sim.unknownCommand",
            "requestId": "req-unknown",
            "sessionId": created["sessionId"],
        }))
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_realtime_manager_extract_ws_token_supports_query_and_cookie():
    manager = _build_manager()
    from_query = SimpleNamespace(headers={}, query_params={"token": "query-token"})
    from_cookie = SimpleNamespace(headers={"cookie": "foo=bar; jwt=cookie-token"}, query_params={})

    assert manager.extract_ws_token(from_query) == "query-token"
    assert manager.extract_ws_token(from_cookie) == "cookie-token"


def test_realtime_manager_extract_ws_token_supports_bearer_header():
    manager = _build_manager()
    websocket = SimpleNamespace(headers={"authorization": "Bearer bearer-token"}, query_params={})

    assert manager.extract_ws_token(websocket) == "bearer-token"


def test_realtime_manager_extract_ws_token_requires_credentials():
    manager = _build_manager()
    websocket = SimpleNamespace(headers={}, query_params={})

    with pytest.raises(HTTPException) as exc:
        manager.extract_ws_token(websocket)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing authentication token"


def test_realtime_manager_cookie_parsing_rate_limit_and_error_payload(monkeypatch):
    manager = _build_manager()
    times = iter([100.0, 101.0, 161.0])

    assert manager.parse_cookie_header("foo=bar; invalid; jwt=abc; spaced = value ") == {
        "foo": "bar",
        "jwt": "abc",
        "spaced": "value",
    }
    assert manager._normalize_ticket_id(" st_1234567890abcdef ") == "1234567890"
    assert manager._normalize_ticket_id("") is None
    assert manager.error_payload(
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

    monkeypatch.setattr("realtime_ws.time.time", lambda: next(times))
    manager.ws_create_rate_limit_per_minute = 2
    assert manager._allow_session_create("sub:user-1") is True
    assert manager._allow_session_create("sub:user-1") is True
    assert manager._allow_session_create("sub:user-1") is True
    manager.ws_create_rate_limit_per_minute = 0
    assert manager._allow_session_create("sub:user-1") is False


def test_realtime_manager_model_description_payload_includes_dimensions():
    manager = _build_manager()

    class _Dimension:
        def __init__(self):
            self.start = 4
            self.valueReference = 7
            self.variable = SimpleNamespace(name="dimensionVar")

    class _Var:
        def __init__(self):
            self.name = "arrayOut"
            self.type = "Float64"
            self.causality = None
            self.variability = None
            self.start = [1.0, 2.0]
            self.unit = "V"
            self.dimensions = [_Dimension()]

    md = SimpleNamespace(
        fmiVersion="3.0",
        coSimulation=True,
        modelExchange=False,
        modelVariables=[_Var()],
    )

    payload = manager.model_description_payload(md)

    assert payload["simulationKind"] == "coSimulation"
    assert payload["variables"][0]["causality"] == "local"
    assert payload["variables"][0]["variability"] == "continuous"
    assert payload["variables"][0]["dimensions"] == [{"start": 4, "valueReference": 7, "variableName": "dimensionVar"}]


def test_realtime_manager_model_description_payload_preserves_wide_integer_starts_as_strings():
    manager = _build_manager()
    md = SimpleNamespace(
        fmiVersion="3.0",
        coSimulation=True,
        modelExchange=False,
        modelVariables=[
            SimpleNamespace(
                name="wideSigned",
                type="Int64",
                causality="parameter",
                variability="discrete",
                start=-9223372036854775808,
                unit=None,
                dimensions=[],
            ),
            SimpleNamespace(
                name="wideUnsigned",
                type="UInt64",
                causality="parameter",
                variability="discrete",
                start=18446744073709551615,
                unit=None,
                dimensions=[],
            ),
        ],
    )

    payload = manager.model_description_payload(md)

    assert payload["variables"][0]["start"] == "-9223372036854775808"
    assert payload["variables"][1]["start"] == "18446744073709551615"


def test_realtime_session_cache_evicts_old_entries():
    session = _build_session()

    for index in range(300):
        session.cache_response(f"req-{index}", {"index": index})

    assert session.get_cached("req-0") is None
    assert session.get_cached("req-43") is None
    assert session.get_cached("req-44") == {"index": 44}
    assert session.get_cached("req-299") == {"index": 299}


@pytest.mark.asyncio
async def test_realtime_session_enqueue_event_replaces_oldest_when_queue_is_full():
    session = _build_session()
    websocket = SimpleNamespace(send_json=lambda payload: None)
    connection = _WsConnection(websocket=websocket, queue_size=1)
    connection.queue.put_nowait({"type": "old"})
    session.connection = connection

    await session._enqueue_event({"type": "new"})

    assert connection.queue.get_nowait() == {"type": "new"}
    assert session._pending_queue_drops == 1


@pytest.mark.asyncio
async def test_realtime_session_heartbeat_emits_expiring_notice_once(monkeypatch):
    session = _build_session()
    session.state = "running"
    session.current_time = 2.5
    session.exp = 105
    monkeypatch.setattr(session.manager, "ws_heartbeat_seconds", 0.01)
    monkeypatch.setattr(session.manager, "ws_expiring_notice_seconds", 10)

    events = []
    sleep_calls = {"count": 0}

    async def _fake_enqueue(payload):
        events.append(payload)

    async def _fake_sleep(_seconds):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(session, "_enqueue_event", _fake_enqueue)
    monkeypatch.setattr("realtime_ws.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("realtime_ws.time.time", lambda: 100)

    await session._heartbeat_loop()

    assert [event["type"] for event in events] == ["session.heartbeat", "session.expiring"]
    assert events[1]["secondsRemaining"] == 5


@pytest.mark.asyncio
async def test_realtime_cleanup_loop_expires_detached_and_closed_sessions(monkeypatch):
    manager = _build_manager()

    class _Session:
        def __init__(self, session_id, *, closed=False, exp=None, connection=None, attach_deadline=None):
            self.session_id = session_id
            self._closed = closed
            self.exp = exp
            self.connection = connection
            self.attach_deadline = attach_deadline
            self.terminated = []

        def is_closed(self):
            return self._closed

        async def terminate(self, reason):
            self.terminated.append(reason)

    closed = _Session("sess-closed", closed=True)
    expired = _Session("sess-expired", exp=10, connection=object())
    detached = _Session("sess-detached", attach_deadline=20)
    manager._sessions = {
        closed.session_id: closed,
        expired.session_id: expired,
        detached.session_id: detached,
    }

    sleep_calls = {"count": 0}

    async def _fake_sleep(_seconds):
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("realtime_ws.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("realtime_ws.time.time", lambda: 30)

    with pytest.raises(asyncio.CancelledError):
        await manager._cleanup_loop()

    assert manager._sessions == {}
    assert expired.terminated == ["expired"]
    assert detached.terminated == ["detached_timeout"]


@pytest.mark.asyncio
async def test_realtime_run_loop_transitions_to_error_on_http_exception(monkeypatch):
    session = _build_session()
    session.state = "running"
    session.stop_time = 5.0

    emitted_states = []

    async def _fake_step_once(_delta_t, emit_outputs=True):
        raise HTTPException(status_code=400, detail="step failed")

    async def _fake_emit_state():
        emitted_states.append(session.state)

    monkeypatch.setattr(session, "_step_once", _fake_step_once)
    monkeypatch.setattr(session, "_emit_state", _fake_emit_state)

    await session._run_loop()

    assert session.state == "error"
    assert emitted_states == ["error"]


@pytest.mark.asyncio
async def test_realtime_emit_outputs_batches_and_resets_drop_counters(monkeypatch):
    session = _build_session()
    session.subscription = _StreamSubscription(period_ms=1, max_batch_size=2, max_hz=None)
    session.seq = 7
    session.current_time = 3.0
    session._pending_queue_drops = 2

    payloads = []
    samples = iter([
        {"y": 1.0},
        {"y": 2.0},
        {"y": 3.0},
    ])
    monotonic_values = iter([10.0, 10.0, 10.5])

    monkeypatch.setattr(session, "_sample_outputs", lambda: next(samples))

    def _fake_monotonic():
        try:
            return next(monotonic_values)
        except StopIteration:
            return 10.5

    monkeypatch.setattr("realtime_ws.time.monotonic", _fake_monotonic)

    async def _fake_enqueue(payload):
        payloads.append(payload)

    monkeypatch.setattr(session, "_enqueue_event", _fake_enqueue)

    await session._emit_outputs_if_needed(force=False)
    await session._emit_outputs_if_needed(force=False)
    await session._emit_outputs_if_needed(force=True)

    assert len(payloads) == 2
    assert payloads[-1]["type"] == "sim.outputs"
    assert payloads[-1]["seq"] == 8
    assert payloads[-1]["batchSize"] == 2
    assert payloads[-1]["values"] == {"y": 3.0}
    assert payloads[-1]["dropped"] == 1
    assert session._pending_queue_drops == 0


@pytest.mark.asyncio
async def test_initialize_fmi3_uses_enter_initialization_mode_without_setup_experiment(monkeypatch):
    from realtime_ws import _RealtimeSession

    class _MockFmu3:
        def __init__(self):
            self.calls = []

        def instantiate(self):
            self.calls.append(("instantiate",))

        def enterInitializationMode(self, **kwargs):
            self.calls.append(("enterInitializationMode", kwargs))

        def exitInitializationMode(self):
            self.calls.append(("exitInitializationMode",))

        def terminate(self):
            self.calls.append(("terminate",))

        def freeInstance(self):
            self.calls.append(("freeInstance",))

    mock_fmu = _MockFmu3()
    session = _RealtimeSession(_realtime_manager, "sess-test", _claims(), Path("/tmp/test.fmu"))

    monkeypatch.setattr("realtime_ws.extract", lambda _path: "/tmp/unzip")
    monkeypatch.setattr("realtime_ws.instantiate_fmu", lambda *_args, **_kwargs: mock_fmu)
    monkeypatch.setattr("realtime_ws.read_model_description", lambda _path: _mock_model_description_fmi3())

    await session.initialize({"startTime": 1.25, "stopTime": 3.5, "stepSize": 0.1})

    assert ("instantiate",) in mock_fmu.calls
    assert ("exitInitializationMode",) in mock_fmu.calls
    assert ("enterInitializationMode", {"startTime": 1.25, "stopTime": 3.5}) in mock_fmu.calls
    assert not any(call[0] == "setupExperiment" for call in mock_fmu.calls)


@pytest.mark.asyncio
async def test_initialize_fmi3_supports_dimensioned_float64_inputs_and_outputs(monkeypatch):
    from realtime_ws import _RealtimeSession

    class _MockFmu3Array:
        def __init__(self):
            self.calls = []

        def instantiate(self):
            self.calls.append(("instantiate",))

        def enterInitializationMode(self, **kwargs):
            self.calls.append(("enterInitializationMode", kwargs))

        def exitInitializationMode(self):
            self.calls.append(("exitInitializationMode",))

        def terminate(self):
            self.calls.append(("terminate",))

        def freeInstance(self):
            self.calls.append(("freeInstance",))

        def getUInt64(self, refs):
            self.calls.append(("getUInt64", tuple(refs)))
            return [3]

        def setFloat64(self, refs, values):
            self.calls.append(("setFloat64", tuple(refs), tuple(values)))

        def getFloat64(self, refs, nValues=None):
            self.calls.append(("getFloat64", tuple(refs), nValues))
            return [10.0, 20.0, 30.0]

    mock_fmu = _MockFmu3Array()
    session = _RealtimeSession(_realtime_manager, "sess-array", _claims(), Path("/tmp/test.fmu"))

    monkeypatch.setattr("realtime_ws.extract", lambda _path: "/tmp/unzip")
    monkeypatch.setattr("realtime_ws.instantiate_fmu", lambda *_args, **_kwargs: mock_fmu)
    monkeypatch.setattr("realtime_ws.read_model_description", lambda _path: _mock_model_description_fmi3_array())

    await session.initialize({"startTime": 0.0, "stopTime": 1.0, "stepSize": 0.1, "inputs": {"u": [1.0, 2.0, 3.0]}})
    outputs = session._get_values(["y"])

    assert ("setFloat64", (9,), (1.0, 2.0, 3.0)) in mock_fmu.calls
    assert ("getFloat64", (10,), 3) in mock_fmu.calls
    assert outputs["y"] == [10.0, 20.0, 30.0]


def test_ws_duplicate_session_create_request_reuses_local_cache():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        created = _create_ws_session(ws, request_id="req-create")

        ws.send_text(json.dumps({"type": "session.create", "requestId": "req-create", "labId": "1"}))
        duplicate = ws.receive_json()

        assert duplicate == created
        assert len(_realtime_manager._sessions) == 1


def test_ws_session_attach_requires_bearer_when_connection_is_unauthenticated(monkeypatch):
    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _unauthorized)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        ws.send_text(json.dumps({"type": "session.attach", "requestId": "req-attach", "sessionId": "sess-any"}))
        payload = ws.receive_json()

        assert payload["type"] == "error"
        assert payload["code"] == "UNAUTHORIZED"


def test_ws_session_attach_requires_session_id():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "session.attach", "requestId": "req-attach"}))
        payload = ws.receive_json()

        assert payload["type"] == "error"
        assert payload["code"] == "INVALID_COMMAND"


def test_ws_requires_existing_session_before_sim_commands():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        ws.send_text(json.dumps({"type": "model.describe", "requestId": "req-model"}))
        payload = ws.receive_json()

        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"


def test_ws_duplicate_command_request_reuses_session_cache():
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        created = _create_ws_session(ws)

        ws.send_text(json.dumps({"type": "session.ping", "requestId": "req-ping", "sessionId": created["sessionId"]}))
        first = ws.receive_json()
        ws.send_text(json.dumps({"type": "session.ping", "requestId": "req-ping", "sessionId": created["sessionId"]}))
        second = ws.receive_json()

        assert first == second
        assert first["type"] == "session.pong"


def test_ws_command_flow_covers_sim_control_paths(monkeypatch):
    seen_inputs = []

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        created = _create_ws_session(ws)
        session = _realtime_manager._sessions[created["sessionId"]]

        async def _fake_initialize(options):
            session.state = "initialized"
            session.current_time = float(options.get("startTime", 0.0))

        async def _fake_start():
            session.state = "running"

        async def _fake_pause():
            session.state = "paused"

        async def _fake_resume():
            session.state = "running"

        async def _fake_reset():
            session.state = "initialized"
            session.current_time = 0.0

        async def _fake_step_once(delta_t, emit_outputs=False):
            session.current_time += delta_t

        async def _fake_run_until(target_time):
            session.current_time = target_time

        async def _fake_terminate(reason="terminated"):
            session.state = "stopped"
            session._closed = True

        monkeypatch.setattr(session, "initialize", _fake_initialize)
        monkeypatch.setattr(session, "start", _fake_start)
        monkeypatch.setattr(session, "pause", _fake_pause)
        monkeypatch.setattr(session, "resume", _fake_resume)
        monkeypatch.setattr(session, "reset", _fake_reset)
        monkeypatch.setattr(session, "_step_once", _fake_step_once)
        monkeypatch.setattr(session, "run_until", _fake_run_until)
        monkeypatch.setattr(session, "terminate", _fake_terminate)
        monkeypatch.setattr(session, "_sample_outputs", lambda: {"y": session.current_time})
        monkeypatch.setattr(session, "_set_values", lambda values: seen_inputs.append(values))
        monkeypatch.setattr(session, "_get_values", lambda variables: {name: 42.0 for name in variables})

        ws.send_text(json.dumps({"type": "sim.initialize", "requestId": "req-init", "sessionId": created["sessionId"], "options": {"startTime": 1.5}}))
        assert ws.receive_json()["state"] == "initialized"

        ws.send_text(json.dumps({"type": "sim.start", "requestId": "req-start", "sessionId": created["sessionId"]}))
        assert ws.receive_json()["state"] == "running"

        ws.send_text(json.dumps({"type": "sim.pause", "requestId": "req-pause", "sessionId": created["sessionId"]}))
        assert ws.receive_json()["state"] == "paused"

        ws.send_text(json.dumps({"type": "sim.resume", "requestId": "req-resume", "sessionId": created["sessionId"]}))
        assert ws.receive_json()["state"] == "running"

        ws.send_text(json.dumps({"type": "sim.reset", "requestId": "req-reset", "sessionId": created["sessionId"]}))
        reset_payload = ws.receive_json()
        assert reset_payload["state"] == "initialized"
        assert reset_payload["simTime"] == 0.0

        ws.send_text(json.dumps({"type": "sim.step", "requestId": "req-step", "sessionId": created["sessionId"], "deltaT": 0.5}))
        step_payload = ws.receive_json()
        assert step_payload["type"] == "sim.outputs"
        assert step_payload["simTime"] == 0.5
        assert step_payload["values"] == {"y": 0.5}

        ws.send_text(json.dumps({"type": "sim.runUntil", "requestId": "req-run-until", "sessionId": created["sessionId"], "time": 2.0}))
        run_until_payload = ws.receive_json()
        assert run_until_payload["simTime"] == 2.0
        assert run_until_payload["values"] == {"y": 2.0}

        ws.send_text(json.dumps({"type": "sim.setInputs", "requestId": "req-set-inputs", "sessionId": created["sessionId"], "values": {"u1": 1.25}}))
        set_inputs_payload = ws.receive_json()
        assert set_inputs_payload["type"] == "sim.inputs.updated"
        assert seen_inputs == [{"u1": 1.25}]

        ws.send_text(json.dumps({"type": "sim.getOutputs", "requestId": "req-get-outputs", "sessionId": created["sessionId"], "variables": ["y"]}))
        get_outputs_payload = ws.receive_json()
        assert get_outputs_payload["values"] == {"y": 42.0}

        ws.send_text(json.dumps({"type": "sim.getState", "requestId": "req-get-state", "sessionId": created["sessionId"]}))
        assert ws.receive_json()["type"] == "sim.state"

        ws.send_text(json.dumps({
            "type": "sim.subscribeOutputs",
            "requestId": "req-subscribe",
            "sessionId": created["sessionId"],
            "variables": ["y"],
            "periodMs": 50,
            "maxBatchSize": 2,
            "maxHz": 5,
        }))
        subscribe_payload = ws.receive_json()
        assert subscribe_payload["type"] == "sim.subscribed"
        assert subscribe_payload["periodMs"] == 50
        assert subscribe_payload["maxBatchSize"] == 2
        assert subscribe_payload["maxHz"] == 5.0

        ws.send_text(json.dumps({"type": "sim.unsubscribeOutputs", "requestId": "req-unsubscribe", "sessionId": created["sessionId"]}))
        assert ws.receive_json()["type"] == "sim.unsubscribed"

        ws.send_text(json.dumps({"type": "session.terminate", "requestId": "req-terminate", "sessionId": created["sessionId"]}))
        terminate_payload = ws.receive_json()
        assert terminate_payload["type"] == "session.closed"
        assert terminate_payload["reason"] == "client_terminated"


def test_ws_command_http_exception_maps_to_reservation_not_active(monkeypatch):
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        created = _create_ws_session(ws)
        session = _realtime_manager._sessions[created["sessionId"]]

        async def _forbidden_resume():
            raise HTTPException(status_code=403, detail="reservation not active")

        monkeypatch.setattr(session, "resume", _forbidden_resume)

        ws.send_text(json.dumps({"type": "sim.resume", "requestId": "req-resume", "sessionId": created["sessionId"]}))
        payload = ws.receive_json()

        assert payload["type"] == "error"
        assert payload["code"] == "RESERVATION_NOT_ACTIVE"


def test_ws_command_unexpected_exception_maps_to_internal_error(monkeypatch):
    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        created = _create_ws_session(ws)
        session = _realtime_manager._sessions[created["sessionId"]]

        def _raise_runtime_error(_variables):
            raise RuntimeError("boom")

        monkeypatch.setattr(session, "_default_output_variables", lambda: ["y"])
        monkeypatch.setattr(session, "_get_values", _raise_runtime_error)

        ws.send_text(json.dumps({"type": "sim.getOutputs", "requestId": "req-get-outputs", "sessionId": created["sessionId"]}))
        payload = ws.receive_json()

        assert payload["type"] == "error"
        assert payload["code"] == "INTERNAL_ERROR"


def test_realtime_default_output_variables_falls_back_to_all_variables():
    session = _build_session()
    session._variables = {
        "u": SimpleNamespace(name="u", causality="input"),
        "p": SimpleNamespace(name="p", causality="parameter"),
    }

    assert session._default_output_variables() == ["u", "p"]


def test_realtime_session_matches_claims_and_reservation_window(monkeypatch):
    session = _build_session()

    assert session.matches_claims(_claims()) is True
    assert session.matches_claims(_claims_with(sub="other")) is False

    monkeypatch.setattr("realtime_ws.time.time", lambda: 5)
    session.nbf = 10
    with pytest.raises(HTTPException) as not_active:
        session.ensure_reservation_window()
    assert not_active.value.status_code == 403

    session.nbf = 0
    session.exp = 5
    with pytest.raises(HTTPException) as expired:
        session.ensure_reservation_window()
    assert expired.value.status_code == 401


def test_realtime_shutdown_fmu_ignores_cleanup_errors(monkeypatch):
    session = _build_session()

    class _BrokenFmu:
        def terminate(self):
            raise RuntimeError("terminate failed")

        def freeInstance(self):
            raise RuntimeError("free failed")

    session._fmu = _BrokenFmu()
    session._unzipdir = "/tmp/test-session"
    monkeypatch.setattr("realtime_ws.shutil.rmtree", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("rm failed")))

    session._shutdown_fmu()

    assert session._fmu is None
    assert session._unzipdir is None


@pytest.mark.asyncio
async def test_realtime_step_once_validates_state_and_emits_progress(monkeypatch):
    session = _build_session()

    with pytest.raises(HTTPException) as not_initialized:
        await session._step_once(0.1)
    assert not_initialized.value.status_code == 409

    class _MockFmu:
        def __init__(self):
            self.calls = []

        def doStep(self, current_time, delta_t):
            self.calls.append((current_time, delta_t))

    progress_events = []
    outputs_called = []
    session._fmu = _MockFmu()
    session.current_time = 1.0

    async def _fake_enqueue(payload):
        progress_events.append(payload)

    async def _fake_emit_outputs_if_needed():
        outputs_called.append(True)

    monkeypatch.setattr(session, "_enqueue_event", _fake_enqueue)
    monkeypatch.setattr(session, "_emit_outputs_if_needed", _fake_emit_outputs_if_needed)

    with pytest.raises(HTTPException) as bad_delta:
        await session._step_once(0)
    assert bad_delta.value.status_code == 400

    await session._step_once(0.5)

    assert session._fmu.calls == [(1.0, 0.5)]
    assert progress_events[0]["type"] == "sim.progress"
    assert session.current_time == 1.5
    assert outputs_called == [True]


@pytest.mark.asyncio
async def test_realtime_session_attach_and_detach_manage_tasks(monkeypatch):
    session = _build_session()
    previous_connection = _WsConnection(websocket=SimpleNamespace(send_json=lambda payload: None), queue_size=1)
    previous_connection.sender_task = asyncio.create_task(asyncio.sleep(60))
    session.connection = previous_connection
    session._heartbeat_task = asyncio.create_task(asyncio.sleep(60))

    sender_tasks = []
    heartbeat_tasks = []
    real_create_task = asyncio.create_task

    def _fake_create_task(coro):
        task = real_create_task(coro)
        code = getattr(coro, "cr_code", None)
        if code is not None and code.co_name == "_sender_loop":
            sender_tasks.append(task)
        else:
            heartbeat_tasks.append(task)
        return task

    monkeypatch.setattr("realtime_ws.asyncio.create_task", _fake_create_task)

    new_connection = _WsConnection(websocket=SimpleNamespace(send_json=lambda payload: None), queue_size=1)
    await session.attach(new_connection)
    await asyncio.sleep(0)

    assert session.connection is new_connection
    assert previous_connection.sender_task.cancelled() is True
    assert sender_tasks[-1] is new_connection.sender_task
    assert session._heartbeat_task is heartbeat_tasks[-1]

    monkeypatch.setattr("realtime_ws.time.time", lambda: 100)
    await session.detach()
    await asyncio.sleep(0)

    assert session.connection is None
    assert session._heartbeat_task is None
    assert new_connection.sender_task.cancelled() is True
    assert session.attach_deadline == 100 + session.manager.ws_attach_grace_seconds

    for task in sender_tasks + heartbeat_tasks:
        if not task.done():
            task.cancel()
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_realtime_sender_loop_sends_payload_and_stops_on_error():
    sent = []

    class _WebSocket:
        async def send_json(self, payload):
            sent.append(payload)
            raise RuntimeError("send failed")

    session = _build_session()
    connection = _WsConnection(websocket=_WebSocket(), queue_size=2)
    await connection.queue.put({"type": "first"})

    await session._sender_loop(connection)

    assert sent == [{"type": "first"}]


def test_realtime_session_dimension_helpers_cover_error_paths():
    session = _build_session()

    assert session._coerce_dimension_extent_value([3]) == 3
    with pytest.raises(HTTPException) as scalar_only:
        session._coerce_dimension_extent_value([1, 2])
    assert scalar_only.value.status_code == 400

    with pytest.raises(HTTPException) as invalid_extent:
        session._coerce_dimension_extent_value("abc")
    assert invalid_extent.value.status_code == 400

    with pytest.raises(HTTPException) as negative_extent:
        session._coerce_dimension_extent_value(-1)
    assert negative_extent.value.status_code == 400

    session._variables_by_value_reference = {}
    with pytest.raises(HTTPException) as unknown_reference:
        session._resolve_dimension_extent(SimpleNamespace(start=None, valueReference=99, variable=None))
    assert unknown_reference.value.status_code == 400

    session._variables_by_value_reference = {
        1: SimpleNamespace(valueReference=1, type="UInt64", start=None),
    }
    session._fmu = SimpleNamespace(getUInt64=lambda refs: [4])
    assert session._resolve_dimension_extent(SimpleNamespace(start=None, valueReference=1, variable=None)) == 4
    assert session._resolve_dimension_extent(SimpleNamespace(start=None, valueReference=None, variable=SimpleNamespace(start=5))) == 5

    with pytest.raises(HTTPException) as unresolved:
        session._resolve_dimension_extent(SimpleNamespace(start=None, valueReference=None, variable=None))
    assert unresolved.value.status_code == 400


def test_realtime_session_normalize_scalar_value_and_model_loading(monkeypatch):
    session = _build_session()
    md = _mock_model_description()
    calls = {"count": 0}

    def _fake_read(_path):
        calls["count"] += 1
        return md

    monkeypatch.setattr("realtime_ws.read_model_description", _fake_read)

    assert session._normalize_variable_type(SimpleNamespace(type="Enumeration")) == "Integer"
    assert session._normalize_scalar_value("Real", 1) == 1.0
    assert session._normalize_scalar_value("Integer", 2.7) == 2
    assert session._normalize_scalar_value("Int64", 9223372036854775807) == "9223372036854775807"
    assert session._normalize_scalar_value("UInt64", 18446744073709551615) == "18446744073709551615"
    assert session._normalize_scalar_value("Boolean", 1) is True
    assert session._normalize_scalar_value("String", b"abc") == "abc"
    assert session._normalize_scalar_value("Binary", b"abc") == "YWJj"
    assert session._normalize_scalar_value("Clock", 1) is True

    session._ensure_model_loaded()
    session._ensure_model_loaded()

    assert calls["count"] == 1
    assert session._model_description is md
    assert "y" in session._variables
    assert 1 in session._variables_by_value_reference


def test_realtime_session_set_and_get_values_cover_type_errors():
    session = _build_session()

    with pytest.raises(HTTPException) as not_initialized:
        session._set_values({"u": 1})
    assert not_initialized.value.status_code == 409

    with pytest.raises(HTTPException) as get_not_initialized:
        session._get_values(["u"])
    assert get_not_initialized.value.status_code == 409

    class _MockFmu:
        def __init__(self):
            self.real_calls = []
            self.bool_calls = []
            self.string_calls = []
            self.binary_calls = []
            self.clock_calls = []

        def setReal(self, refs, values):
            self.real_calls.append((refs, values))

        def setBoolean(self, refs, values):
            self.bool_calls.append((refs, values))

        def setString(self, refs, values):
            self.string_calls.append((refs, values))

        def setBinary(self, refs, values):
            self.binary_calls.append((refs, values))

        def setClock(self, refs, values):
            self.clock_calls.append((refs, values))

        def getReal(self, refs):
            return [3.5]

        def getBoolean(self, refs):
            return [1]

        def getString(self, refs):
            return [b"ok"]

        def getBinary(self, refs):
            return [b"\x01\x02"]

        def getClock(self, refs):
            return [1]

    session._fmu = _MockFmu()
    session._variables = {
        "real": SimpleNamespace(name="real", valueReference=1, type="Real", dimensions=[]),
        "flag": SimpleNamespace(name="flag", valueReference=2, type="Boolean", dimensions=[]),
        "text": SimpleNamespace(name="text", valueReference=3, type="String", dimensions=[]),
        "blob": SimpleNamespace(name="blob", valueReference=4, type="Binary", dimensions=[]),
        "tick": SimpleNamespace(name="tick", valueReference=5, type="Clock", dimensions=[]),
    }

    session._set_values({"real": 1, "flag": 1, "text": 9, "blob": "AQI=", "tick": 1, "ignored": 4})
    outputs = session._get_values(["real", "flag", "text", "blob", "tick", "missing"])

    assert session._fmu.real_calls == [([1], [1.0])]
    assert session._fmu.bool_calls == [([2], [True])]
    assert session._fmu.string_calls == [([3], ["9"])]
    assert session._fmu.binary_calls == [([4], [b"\x01\x02"])]
    assert session._fmu.clock_calls == [([5], [True])]
    assert outputs == {"real": 3.5, "flag": True, "text": "ok", "blob": "AQI=", "tick": True}

    session._variables["enum"] = SimpleNamespace(name="enum", valueReference=4, type="Enumeration", dimensions=[])
    with pytest.raises(HTTPException) as unsupported_setter:
        session._set_values({"enum": 2})
    assert unsupported_setter.value.status_code == 400

    session._variables = {"enum": SimpleNamespace(name="enum", valueReference=4, type="Enumeration", dimensions=[])}
    with pytest.raises(HTTPException) as unsupported_getter:
        session._get_values(["enum"])
    assert unsupported_getter.value.status_code == 400


def test_realtime_session_set_and_get_values_support_extended_fmi3_integer_widths():
    session = _build_session()

    class _MockFmu:
        def __init__(self):
            self.calls = []

        def setInt8(self, refs, values):
            self.calls.append(("setInt8", refs, values))

        def setUInt16(self, refs, values):
            self.calls.append(("setUInt16", refs, values))

        def setInt64(self, refs, values):
            self.calls.append(("setInt64", refs, values))

        def setUInt64(self, refs, values):
            self.calls.append(("setUInt64", refs, values))

        def getInt8(self, refs):
            self.calls.append(("getInt8", refs))
            return [-5]

        def getUInt16(self, refs):
            self.calls.append(("getUInt16", refs))
            return [512]

        def getInt64(self, refs):
            self.calls.append(("getInt64", refs))
            return [1234567890123]

        def getUInt64(self, refs):
            self.calls.append(("getUInt64", refs))
            return [18446744073709551615]

    session._fmu = _MockFmu()
    session._variables = {
        "smallSigned": SimpleNamespace(name="smallSigned", valueReference=1, type="Int8", dimensions=[]),
        "smallUnsigned": SimpleNamespace(name="smallUnsigned", valueReference=2, type="UInt16", dimensions=[]),
        "wideSigned": SimpleNamespace(name="wideSigned", valueReference=3, type="Int64", dimensions=[]),
        "wideUnsigned": SimpleNamespace(name="wideUnsigned", valueReference=4, type="UInt64", dimensions=[]),
    }

    session._set_values({
        "smallSigned": -4,
        "smallUnsigned": 500,
        "wideSigned": "-9223372036854775808",
        "wideUnsigned": "18446744073709551615",
    })
    outputs = session._get_values(["smallSigned", "smallUnsigned", "wideSigned", "wideUnsigned"])

    assert session._fmu.calls[:4] == [
        ("setInt8", [1], [-4]),
        ("setUInt16", [2], [500]),
        ("setInt64", [3], [-9223372036854775808]),
        ("setUInt64", [4], [18446744073709551615]),
    ]
    assert outputs == {
        "smallSigned": -5,
        "smallUnsigned": 512,
        "wideSigned": "1234567890123",
        "wideUnsigned": "18446744073709551615",
    }


@pytest.mark.asyncio
async def test_realtime_session_terminate_notifies_attached_client_on_expiry():
    sent = []

    class _WebSocket:
        async def send_json(self, payload):
            sent.append(payload)

    session = _build_session()
    session.connection = _WsConnection(websocket=_WebSocket(), queue_size=1)
    session.connection.sender_task = asyncio.create_task(asyncio.sleep(60))
    session._heartbeat_task = asyncio.create_task(asyncio.sleep(60))

    await session.terminate(reason="expired")
    await asyncio.sleep(0)

    assert sent == [{
        "type": "session.closed",
        "sessionId": session.session_id,
        "reason": "expired",
    }]


@pytest.mark.asyncio
async def test_realtime_session_start_pause_resume_reset_run_until_and_terminate(monkeypatch):
    released = []
    manager = _build_manager()
    manager.release_slot = lambda lab_id: released.append(lab_id)
    session = _build_session(manager=manager)
    session._fmu = SimpleNamespace(
        terminate=lambda: None,
        freeInstance=lambda: None,
    )
    session.state = "initialized"
    session.step_size = 0.5
    session.stop_time = 2.0
    session.lab_id = "1"

    emitted = []
    runner_tasks = []

    async def _fake_emit_state():
        emitted.append((session.state, session.current_time))

    async def _fake_run_loop():
        await asyncio.sleep(60)

    async def _fake_initialize(options):
        session.current_time = options["startTime"]
        session.stop_time = options["stopTime"]
        session.step_size = options["stepSize"]

    async def _fake_step_once(delta_t, emit_outputs=False):
        session.current_time += delta_t

    monkeypatch.setattr(session, "_emit_state", _fake_emit_state)
    monkeypatch.setattr(session, "_run_loop", _fake_run_loop)
    monkeypatch.setattr(session, "initialize", _fake_initialize)
    monkeypatch.setattr(session, "_step_once", _fake_step_once)

    real_create_task = asyncio.create_task

    def _fake_create_task(coro):
        task = real_create_task(coro)
        runner_tasks.append(task)
        return task

    monkeypatch.setattr("realtime_ws.asyncio.create_task", _fake_create_task)

    await session.start()
    assert session.state == "running"

    await session.start()
    assert len(runner_tasks) == 1

    await session.pause()
    await asyncio.sleep(0)
    assert session.state == "paused"
    assert runner_tasks[0].cancelled() is True

    session.state = "stopped"
    with pytest.raises(HTTPException) as invalid_resume:
        await session.resume()
    assert invalid_resume.value.status_code == 409

    session.state = "initialized"
    await session.resume()
    assert session.state == "running"

    session.current_time = 1.0
    session.stop_time = 3.0
    session.step_size = 0.25
    session._model_description = object()
    await session.reset()
    assert session.current_time == 0.0

    session.current_time = 0.0
    session.step_size = 0.5
    await session.run_until(1.1)
    assert session.current_time == 1.1
    await session.run_until(1.0)
    assert session.current_time == 1.1

    session.connection = _WsConnection(websocket=SimpleNamespace(send_json=lambda payload: None), queue_size=1)
    session.connection.sender_task = asyncio.create_task(asyncio.sleep(60))
    session._heartbeat_task = asyncio.create_task(asyncio.sleep(60))
    event_payloads = []

    async def _fake_enqueue(payload):
        event_payloads.append(payload)

    monkeypatch.setattr(session, "_enqueue_event", _fake_enqueue)
    await session.terminate(reason="client_terminated")
    await asyncio.sleep(0)

    assert session.state == "stopped"
    assert session.is_closed() is True
    assert released == ["1"]
    assert event_payloads[0]["type"] == "session.closed"

    await session.terminate(reason="again")
    assert released == ["1"]


@pytest.mark.asyncio
async def test_realtime_manager_start_and_stop_manage_cleanup_task():
    manager = _build_manager()

    class _Session:
        def __init__(self, session_id):
            self.session_id = session_id
            self.terminated = []

        async def terminate(self, reason):
            self.terminated.append(reason)

    session = _Session("sess-1")
    manager._sessions = {session.session_id: session}

    await manager.start()
    first_task = manager._cleanup_task
    assert first_task is not None

    await manager.start()
    assert manager._cleanup_task is first_task

    await manager.stop()
    await asyncio.sleep(0)

    assert manager._cleanup_task is None
    assert manager._sessions == {}
    assert session.terminated == ["service_shutdown"]


def test_ws_session_create_maps_ticket_redeem_failures(monkeypatch):
    async def _unauthorized(_token: str):
        raise HTTPException(status_code=401, detail="missing token")

    async def _redeem(*, session_ticket: str, lab_id: str | None, reservation_key: str | None, request_id: str | None = None):
        if session_ticket == "st_expired":
            raise HTTPException(status_code=401, detail="invalid ticket")
        if session_ticket == "st_forbidden":
            raise HTTPException(status_code=403, detail={"message": "forbidden"})
        raise HTTPException(status_code=500, detail={"error": "backend down"})

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _unauthorized)
    monkeypatch.setattr(_realtime_manager, "redeem_session_ticket", _redeem)

    with client.websocket_connect("/api/v1/fmu/sessions") as ws:
        for request_id, ticket, expected_code in (
            ("req-expired", "st_expired", "SESSION_TICKET_INVALID"),
            ("req-forbidden", "st_forbidden", "FORBIDDEN"),
            ("req-error", "st_error", "INTERNAL_ERROR"),
        ):
            ws.send_text(json.dumps({
                "type": "session.create",
                "requestId": request_id,
                "labId": "1",
                "sessionTicket": ticket,
            }))
            payload = ws.receive_json()
            assert payload["type"] == "error"
            assert payload["code"] == expected_code


def test_ws_top_level_http_exception_maps_to_forbidden(monkeypatch):
    async def _forbidden(_token: str):
        raise HTTPException(status_code=403, detail="bad token")

    monkeypatch.setattr(_realtime_manager, "verify_jwt_token", _forbidden)

    with client.websocket_connect("/api/v1/fmu/sessions?token=test-token") as ws:
        payload = ws.receive_json()
        assert payload["type"] == "error"
        assert payload["code"] == "FORBIDDEN"
