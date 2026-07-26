import asyncio
import json
import sys
import time
import zipfile
from collections import deque
from types import SimpleNamespace

import pytest

from probe_proxy_stream import (
    ProxyMetadata,
    ProxyProbeError,
    _receive_stream_samples,
    _send_command,
    load_proxy_metadata,
    main,
    run_probe,
    validate_stream_samples,
)


VALID_MODEL_DESCRIPTION = """<fmiModelDescription fmiVersion="3.0" modelName="StateSpace">
<CoSimulation modelIdentifier="decentralabs_proxy"/>
<ModelVariables><Float64 name="y" valueReference="1" causality="output"/></ModelVariables>
</fmiModelDescription>"""


def _write_proxy(path, config, model_description=VALID_MODEL_DESCRIPTION):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("modelDescription.xml", model_description)
        archive.writestr("resources/config.json", json.dumps(config))
        archive.writestr("binaries/x86_64-windows/decentralabs_proxy.dll", b"runtime")


def test_load_proxy_metadata_reads_config_and_outputs(tmp_path):
    proxy = tmp_path / "statespace-proxy.fmu"
    _write_proxy(proxy, {
        "gatewayWsUrl": "wss://localhost:8443/fmu/api/v1/fmu/sessions",
        "labId": "lab-1",
        "reservationKey": "reservation-1",
        "sessionTicket": "st_ticket",
        "ticketExpiresAt": int(time.time()) + 60,
    })

    metadata = load_proxy_metadata(proxy)

    assert metadata.model_name == "StateSpace"
    assert metadata.output_names == ["y"]
    assert metadata.gateway_ws_url.endswith("/fmu/sessions")
    assert metadata.session_ticket == "st_ticket"


def test_load_proxy_metadata_rejects_expired_ticket(tmp_path):
    proxy = tmp_path / "expired.fmu"
    _write_proxy(proxy, {
        "gatewayWsUrl": "wss://localhost:8443/fmu/api/v1/fmu/sessions",
        "labId": "lab-1",
        "reservationKey": "reservation-1",
        "sessionTicket": "st_ticket",
        "ticketExpiresAt": int(time.time()) - 1,
    })

    with pytest.raises(ProxyProbeError, match="caducado"):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_rejects_missing_file(tmp_path):
    with pytest.raises(ProxyProbeError, match="No existe"):
        load_proxy_metadata(tmp_path / "missing.fmu")


def test_load_proxy_metadata_rejects_invalid_zip(tmp_path):
    proxy = tmp_path / "invalid.fmu"
    proxy.write_bytes(b"not a zip")

    with pytest.raises(ProxyProbeError, match="FMU/ZIP válido"):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_rejects_missing_runtime(tmp_path):
    proxy = tmp_path / "no-runtime.fmu"
    with zipfile.ZipFile(proxy, "w") as archive:
        archive.writestr("modelDescription.xml", "<fmiModelDescription/>")
        archive.writestr("resources/config.json", "{}")

    with pytest.raises(ProxyProbeError, match="runtime decentralabs_proxy"):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_rejects_missing_config_entry(tmp_path):
    proxy = tmp_path / "missing-config.fmu"
    with zipfile.ZipFile(proxy, "w") as archive:
        archive.writestr("modelDescription.xml", VALID_MODEL_DESCRIPTION)
        archive.writestr("binaries/x86_64-windows/decentralabs_proxy.dll", b"runtime")

    with pytest.raises(ProxyProbeError, match="config.json"):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_rejects_non_object_config(tmp_path):
    proxy = tmp_path / "list-config.fmu"
    _write_proxy(proxy, ["not", "an", "object"])

    with pytest.raises(ProxyProbeError, match="objeto JSON"):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_rejects_missing_model_attributes(tmp_path):
    proxy = tmp_path / "missing-model-attributes.fmu"
    _write_proxy(proxy, {}, "<fmiModelDescription/>")

    with pytest.raises(ProxyProbeError, match="modelName/fmiVersion"):
        load_proxy_metadata(proxy)


@pytest.mark.parametrize(
    ("config", "model_description", "message"),
    [
        ({}, None, "gatewayWsUrl"),
        ({"gatewayWsUrl": "http://gateway"}, None, "ws://"),
        ({"gatewayWsUrl": "ws://gateway", "sessionTicket": "st", "ticketExpiresAt": "bad"}, None, "timestamp"),
        ({"gatewayWsUrl": "ws://gateway", "sessionTicket": "st", "ticketExpiresAt": "nan"}, None, "finito"),
        ({"gatewayWsUrl": "ws://gateway", "sessionTicket": "st", "ticketExpiresAt": 9999999999}, None, "labId"),
        ({"gatewayWsUrl": "ws://gateway", "labId": "lab", "reservationKey": "res", "sessionTicket": "st", "ticketExpiresAt": 9999999999}, "<broken", "metadata"),
        ({"gatewayWsUrl": "ws://gateway", "labId": "lab", "reservationKey": "res", "sessionTicket": "st", "ticketExpiresAt": 9999999999}, "<fmiModelDescription modelName='x' fmiVersion='3.0'/>", "Co-Simulation"),
        ({"gatewayWsUrl": "ws://gateway", "labId": "lab", "reservationKey": "res", "sessionTicket": "st", "ticketExpiresAt": 9999999999}, "<fmiModelDescription modelName='x' fmiVersion='3.0'><CoSimulation/></fmiModelDescription>", "ninguna salida"),
    ],
)
def test_load_proxy_metadata_rejects_invalid_metadata(tmp_path, config, model_description, message):
    proxy = tmp_path / "invalid-metadata.fmu"
    _write_proxy(proxy, config, VALID_MODEL_DESCRIPTION if model_description is None else model_description)

    with pytest.raises(ProxyProbeError, match=message):
        load_proxy_metadata(proxy)


def test_load_proxy_metadata_can_use_an_explicit_ticket_override(tmp_path):
    proxy = tmp_path / "old-proxy.fmu"
    _write_proxy(proxy, {
        "gatewayWsUrl": "ws://gateway",
        "labId": "lab-1",
        "reservationKey": "reservation-1",
        "sessionTicket": "old-ticket",
        "ticketExpiresAt": int(time.time()) - 1,
    })

    metadata = load_proxy_metadata(proxy, validate_ticket=False)

    assert metadata.session_ticket == "old-ticket"


def test_validate_stream_samples_checks_sequence_time_and_outputs():
    samples = [
        {"seq": 0, "simTime": 0.01, "values": {"y": [1, 2, 3]}},
        {"seq": 1, "simTime": 0.02, "values": {"y": [2, 3, 4]}},
    ]

    summary = validate_stream_samples(samples, ["y"])

    assert summary["count"] == 2
    assert summary["firstTime"] == 0.01
    assert summary["lastTime"] == 0.02
    assert summary["dropped"] == 0


def test_validate_stream_samples_rejects_missing_output():
    with pytest.raises(ProxyProbeError, match="salida y"):
        validate_stream_samples([
            {"seq": 0, "simTime": 0.01, "values": {}},
        ], ["y"])


@pytest.mark.parametrize(
    ("samples", "message"),
    [
        (["not-an-event"], "inválido"),
        ([{"simTime": 0.01, "values": {"y": [1]}}], "seq/simTime"),
        ([{"seq": 1, "simTime": 0.01, "values": {"y": [1]}}, {"seq": 1, "simTime": 0.02, "values": {"y": [2]}}], "secuencia"),
        ([{"seq": 1, "simTime": 0.02, "values": {"y": [1]}}, {"seq": 2, "simTime": 0.01, "values": {"y": [2]}}], "tiempo"),
        ([{"seq": 1, "simTime": 0.01, "values": []}], "values"),
        ([{"seq": 1, "simTime": 0.01, "values": {"y": [1]}, "dropped": "bad"}], "dropped"),
    ],
)
def test_validate_stream_samples_rejects_malformed_events(samples, message):
    with pytest.raises(ProxyProbeError, match=message):
        validate_stream_samples(samples, ["y"])


def test_validate_stream_samples_rejects_empty_stream():
    with pytest.raises(ProxyProbeError, match="ningún evento"):
        validate_stream_samples([], ["y"])


class _ResponseWebSocket:
    def __init__(self, response):
        self.response = response

    async def send(self, _message):
        return None

    async def recv(self):
        return self.response


@pytest.mark.parametrize("response", ["not-json", "[]", '{"type":"error","requestId":"wrong"}'])
def test_send_command_rejects_malformed_gateway_messages(response):
    with pytest.raises(ProxyProbeError):
        asyncio.run(_send_command(_ResponseWebSocket(response), "test", {}, 1, [], 0.1))


class _ErrorResponseWebSocket(_ResponseWebSocket):
    async def send(self, raw_message):
        self.request_id = json.loads(raw_message)["requestId"]

    async def recv(self):
        return json.dumps({"type": "error", "requestId": self.request_id, "code": "TEST", "message": "rejected"})


def test_send_command_surfaces_gateway_error():
    with pytest.raises(ProxyProbeError, match=r"rejected \[TEST\]"):
        asyncio.run(_send_command(_ErrorResponseWebSocket(None), "test", {}, 1, [], 0.1))


@pytest.mark.parametrize("events", [[None, {"type": "sim.outputs", "seq": 0, "simTime": 0.01, "values": {"y": [1]}}], [{"type": "error", "code": "TEST", "message": "stream failed"}]])
def test_receive_stream_samples_handles_non_output_events(events):
    if events and events[0].get("type") == "error" if isinstance(events[0], dict) else False:
        expected = "stream failed"
    else:
        expected = None
    if expected:
        with pytest.raises(ProxyProbeError, match=expected):
            asyncio.run(_receive_stream_samples(_ResponseWebSocket(None), events, 1, 0.1))
    else:
        samples = asyncio.run(_receive_stream_samples(_ResponseWebSocket(None), events, 1, 0.1))
        assert samples[0]["seq"] == 0


def test_receive_stream_samples_rejects_non_json():
    with pytest.raises(ProxyProbeError, match="no JSON"):
        asyncio.run(_receive_stream_samples(_ResponseWebSocket("not-json"), [], 1, 0.1))


class _FakeWebSocket:
    def __init__(self):
        self.messages = deque()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def send(self, raw_message):
        message = json.loads(raw_message)
        request_id = message["requestId"]
        message_type = message["type"]
        if message_type == "session.create":
            self.messages.append({"type": "session.created", "requestId": request_id, "sessionId": "sess-test"})
        elif message_type == "model.describe":
            self.messages.append({"type": "model.description", "requestId": request_id})
        elif message_type == "sim.initialize":
            self.messages.append({"type": "sim.state", "sessionId": "sess-test", "state": "initialized"})
            self.messages.append({"type": "sim.state", "requestId": request_id, "sessionId": "sess-test", "state": "initialized"})
        elif message_type == "sim.subscribeOutputs":
            self.messages.append({"type": "sim.subscribed", "requestId": request_id})
        elif message_type == "sim.start":
            self.messages.append({"type": "sim.state", "sessionId": "sess-test", "state": "running"})
            self.messages.append({"type": "sim.outputs", "seq": 0, "simTime": 0.01, "values": {"y": [1, 2, 3]}})
            self.messages.append({"type": "sim.outputs", "seq": 1, "simTime": 0.02, "values": {"y": [2, 3, 4]}})
            self.messages.append({"type": "sim.state", "requestId": request_id, "sessionId": "sess-test", "state": "running"})
        elif message_type == "sim.pause":
            self.messages.append({"type": "sim.state", "requestId": request_id, "sessionId": "sess-test", "state": "paused"})
        elif message_type == "session.terminate":
            self.messages.append({"type": "session.closed", "requestId": request_id, "sessionId": "sess-test"})
        else:
            raise AssertionError(f"Unexpected command: {message_type}")

    async def recv(self):
        if not self.messages:
            raise AssertionError("The probe attempted to read beyond the fake stream")
        return json.dumps(self.messages.popleft())


def test_run_probe_executes_realtime_lifecycle(monkeypatch, tmp_path):
    fake_websocket = _FakeWebSocket()

    class _FakeConnect:
        async def __aenter__(self):
            return fake_websocket

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=lambda *_args, **_kwargs: _FakeConnect()))
    metadata = ProxyMetadata(
        proxy_path=tmp_path / "statespace-proxy.fmu",
        model_name="StateSpace",
        fmi_version="3.0",
        output_names=["y"],
        gateway_ws_url="ws://gateway.test/fmu/api/v1/fmu/sessions",
        lab_id="lab-1",
        reservation_key="reservation-1",
        session_ticket="st_ticket",
        ticket_expires_at=time.time() + 60,
    )

    result = asyncio.run(run_probe(
        metadata,
        gateway_ws_url=None,
        session_ticket=None,
        lab_id=None,
        reservation_key=None,
        sample_count=2,
        stop_time=1.0,
        step_size=0.01,
        period_ms=20,
        timeout=1.0,
        insecure=False,
    ))

    assert result["status"] == "PASS"
    assert result["stream"]["count"] == 2
