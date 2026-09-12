import json

import pytest

import heartbeat_stream


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
        {"name": "lab-ws-01"},
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
