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


def test_realtime_manager_extract_ws_token_requires_credentials():
    manager = _build_manager()
    websocket = SimpleNamespace(headers={}, query_params={})

    with pytest.raises(HTTPException) as exc:
        manager.extract_ws_token(websocket)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Missing authentication token"


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
