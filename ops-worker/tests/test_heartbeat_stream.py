import json

import pytest
import requests

import heartbeat_stream


def test_format_sse_event_contract_preserves_wire_framing():
    assert heartbeat_stream.format_sse_event("heartbeat", '{"ready":true}') == (
        'event: heartbeat\ndata: {"ready":true}\n\n'
    )


class TrustFailure(ValueError):
    def __init__(self, code):
        super().__init__("trust failed")
        self.code = code


class Logger:
    def __init__(self):
        self.info_calls = []
        self.exception_calls = []

    def info(self, *args):
        self.info_calls.append(args)

    def exception(self, *args):
        self.exception_calls.append(args)


def _stream(**overrides):
    dependencies = {
        "poll_heartbeat": lambda _host, include_events=False: {
            "heartbeat": {"summary": {"ready": True}},
            "last_event": None,
        },
        "format_sse_event": lambda event, data: f"{event}:{data}",
        "trust_error_type": TrustFailure,
        "missing_credentials_predicate": lambda _exc: False,
        "trust_error_payload": lambda host, code: {"host": host, "code": code},
        "request_id": lambda: "request-1",
        "logger": Logger(),
        "sanitize_log_value": lambda value: value,
        "credentials_required_message": "WinRM credentials are required",
        "heartbeat_interval_seconds": 0,
        "sleep": lambda _seconds: None,
    }
    dependencies.update(overrides)
    return heartbeat_stream.generate_heartbeat_stream(
        {
            "name": "lab-ws-01",
            "address": "192.168.1.50",
            "winrm_port": 5986,
        },
        include_events=False,
        **dependencies,
    ), dependencies


def test_heartbeat_stream_emits_heartbeat_payload_and_host():
    stream, _dependencies = _stream()

    chunk = next(stream)

    assert chunk.startswith("heartbeat:")
    payload = json.loads(chunk.split(":", 1)[1])
    assert payload["host"] == "lab-ws-01"
    assert payload["heartbeat"]["summary"]["ready"] is True


def test_heartbeat_stream_emits_trust_error_and_stops():
    stream, dependencies = _stream(
        poll_heartbeat=lambda _host, include_events=False: (_ for _ in ()).throw(
            TrustFailure("WINRM_TRUST_REQUIRED")
        ),
    )

    chunk = next(stream)
    assert chunk == 'error:{"host": "lab-ws-01", "code": "WINRM_TRUST_REQUIRED"}'
    with pytest.raises(StopIteration):
        next(stream)
    assert dependencies["logger"].info_calls


def test_heartbeat_stream_emits_actionable_unavailable_error_for_network_failure():
    stream, dependencies = _stream(
        poll_heartbeat=lambda _host, include_events=False: (_ for _ in ()).throw(
            requests.exceptions.ConnectTimeout("station is off")
        ),
    )

    chunk = next(stream)
    payload = json.loads(chunk.split(":", 1)[1])

    assert payload == {
        "error": "Lab Station is unreachable over WinRM",
        "code": "WINRM_UNREACHABLE",
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "port": 5986,
    }
    assert not payload.get("requestId")
    assert dependencies["logger"].exception_calls == []
