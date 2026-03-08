import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


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
