from datetime import datetime
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from session_observation_context import SessionObservationContext
from session_observation_runtime import (
    SessionObservationRuntime,
    create_session_observation_runtime,
)


def _context(**overrides):
    values = {
        "get_session_observations_factory": lambda: SimpleNamespace,
        "get_db_engine": lambda: "ops-db",
        "get_guacamole_db_engine": lambda: "guac-db",
        "get_encrypt_secret": lambda: lambda value: f"enc:{value}",
        "get_decrypt_secret": lambda: lambda value: f"dec:{value}",
        "get_http_get": lambda: "http-get",
        "get_http_post": lambda: "http-post",
        "get_http_delete": lambda: "http-delete",
        "get_sql_text": lambda: "sql-text",
        "get_integrity_error_type": lambda: RuntimeError,
        "get_enqueue_session_observation": lambda: lambda payload: (
            "enqueued",
            payload,
        ),
        "get_retry_delay": lambda: lambda attempts: attempts + 1,
        "get_to_utc": lambda: lambda value: ("utc", value),
        "get_now": lambda: lambda: datetime(2026, 1, 1),
        "get_current_epoch": lambda: lambda: 123.0,
        "get_config": lambda: {
            "access_audit_url": "https://audit",
            "session_observer_gateway_id": "gateway-1",
            "session_observer_signing_secret": "signing-secret",
            "session_observation_outbox_enabled": True,
            "session_observation_outbox_batch_size": 20,
            "session_observation_outbox_max_attempts": 4,
            "session_observation_outbox_request_timeout_seconds": 5,
            "guac_admin_user": "admin",
            "guac_admin_pass": "password",
            "guac_api_url": "https://guac",
            "guac_token_revocation_max_attempts": 3,
            "guacamole_history_lookback_seconds": 30,
            "guacamole_history_reconciliation_retention_seconds": 300,
        },
        "get_logger": lambda: "logger",
        "get_service": lambda: None,
    }
    values.update(overrides)
    return SessionObservationContext(**values)


def test_session_observation_runtime_builds_service_from_explicit_context():
    captured = {}

    class FakeSessionObservations:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    context = _context(get_session_observations_factory=lambda: FakeSessionObservations)
    runtime = create_session_observation_runtime(context)

    assert isinstance(runtime, SessionObservationRuntime)
    runtime.create_service()

    assert captured["db_engine"] == "ops-db"
    assert captured["guacamole_db_engine"] == "guac-db"
    assert captured["http_get"] == "http-get"
    assert captured["http_post"] == "http-post"
    assert captured["http_delete"] == "http-delete"
    assert captured["sql_text"] == "sql-text"
    assert captured["integrity_error_type"] is RuntimeError
    assert captured["retry_delay"](2) == 3
    assert captured["encrypt_secret"]("token") == "enc:token"
    assert captured["decrypt_secret"]("cipher") == "dec:cipher"
    assert captured["enqueue_session_observation"]({"id": 1}) == (
        "enqueued",
        {"id": 1},
    )
    assert captured["config"] == {
        "access_audit_url": "https://audit",
        "session_observer_gateway_id": "gateway-1",
        "session_observer_signing_secret": "signing-secret",
        "session_observation_outbox_enabled": True,
        "session_observation_outbox_batch_size": 20,
        "session_observation_outbox_max_attempts": 4,
        "session_observation_outbox_request_timeout_seconds": 5,
        "guac_admin_user": "admin",
        "guac_admin_pass": "password",
        "guac_api_url": "https://guac",
        "guac_token_revocation_max_attempts": 3,
        "guacamole_history_lookback_seconds": 30,
        "guacamole_history_reconciliation_retention_seconds": 300,
    }


def test_session_observation_context_resolves_mutable_dependencies_at_use_time():
    retry_delay = lambda _attempts: 1
    service = object()
    context = _context(
        get_retry_delay=lambda: retry_delay,
        get_service=lambda: service,
    )
    runtime = create_session_observation_runtime(context)

    retry_delay = lambda _attempts: 9
    assert runtime.retry_delay_seconds(1) == 9
    assert runtime._service() is service

    with pytest.raises(FrozenInstanceError):
        context.get_service = lambda: None


def test_session_observation_runtime_forwards_service_operations():
    calls = []

    class FakeService:
        def enqueue_guacamole_token_revocation(self, payload):
            calls.append(("enqueue-revocation", payload))
            return True

        def guacamole_admin_session(self):
            return ("token", "mysql")

        def guacamole_connection_history_observed(self, row):
            return row["observed"]

        def reconcile_guacamole_observations(self, token, source):
            calls.append(("reconcile", token, source))

        def process_guacamole_token_revocations(self):
            return 2

        def enqueue_session_observation(self, payload):
            calls.append(("enqueue-observation", payload))
            return False

        def claim_session_observation_outbox_rows(self):
            return [{"id": 1}]

        def mark_session_observation_delivered(self, record_id):
            calls.append(("delivered", record_id))

        def mark_session_observation_failure(self, record, error):
            calls.append(("failure", record, error))

        def session_observed_epoch(self, value):
            return int(value)

        def base64url_json(self, value):
            return "encoded"

        def session_observer_authorization(self):
            return "Bearer token"

        def deliver_session_observation_outbox(self):
            return 3

    service = FakeService()
    context = _context(
        get_service=lambda: service,
        get_retry_delay=lambda: lambda attempts: attempts + 1,
        get_encrypt_secret=lambda: lambda value: f"enc:{value}",
        get_decrypt_secret=lambda: lambda value: f"dec:{value}",
    )
    runtime = create_session_observation_runtime(context)

    assert runtime.retry_delay_seconds(2) == 3
    assert runtime.encrypt_runtime_secret("token") == "enc:token"
    assert runtime.decrypt_runtime_secret("cipher") == "dec:cipher"
    assert runtime.enqueue_guacamole_token_revocation({"id": 1}) is True
    assert runtime.guacamole_admin_session() == ("token", "mysql")
    assert runtime.guacamole_connection_history_observed({"observed": "time"}) == "time"
    assert runtime.reconcile_guacamole_observations("token", "mysql") is None
    assert runtime.process_guacamole_token_revocations() == 2
    assert runtime.enqueue_session_observation({"id": 2}) is False
    assert runtime.claim_session_observation_outbox_rows() == [{"id": 1}]
    assert runtime.mark_session_observation_delivered(1) is None
    assert runtime.mark_session_observation_failure({"id": 1}, "failed") is None
    assert runtime.session_observed_epoch(7) == 7
    assert runtime.base64url_json({"id": 1}) == "encoded"
    assert runtime.session_observer_authorization() == "Bearer token"
    assert runtime.deliver_session_observation_outbox() == 3
    assert calls == [
        ("enqueue-revocation", {"id": 1}),
        ("reconcile", "token", "mysql"),
        ("enqueue-observation", {"id": 2}),
        ("delivered", 1),
        ("failure", {"id": 1}, "failed"),
    ]
