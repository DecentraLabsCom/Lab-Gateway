from types import SimpleNamespace

from session_observation_runtime import (
    SessionObservationRuntime,
    create_session_observation_runtime,
)


def test_session_observation_runtime_builds_service_from_live_providers():
    captured = {}

    class FakeSessionObservations:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    providers = {
        "SessionObservations": FakeSessionObservations,
        "DB_ENGINE": "ops-db",
        "GUACAMOLE_DB_ENGINE": "guac-db",
        "_encrypt_runtime_secret": lambda value: f"enc:{value}",
        "_decrypt_runtime_secret": lambda value: f"dec:{value}",
        "requests": SimpleNamespace(
            get="http-get", post="http-post", delete="http-delete"
        ),
        "text": "sql-text",
        "IntegrityError": RuntimeError,
        "enqueue_session_observation": lambda payload: ("enqueued", payload),
        "session_observation_retry_delay_seconds": lambda attempts: attempts + 1,
        "to_utc": lambda value: ("utc", value),
        "datetime": SimpleNamespace(now=lambda timezone: ("now", timezone)),
        "timezone": SimpleNamespace(utc="UTC"),
        "time": SimpleNamespace(time="epoch"),
        "ACCESS_AUDIT_URL": "https://audit",
        "SESSION_OBSERVER_GATEWAY_ID": "gateway-1",
        "SESSION_OBSERVER_SIGNING_SECRET": "signing-secret",
        "SESSION_OBSERVATION_OUTBOX_ENABLED": True,
        "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE": 20,
        "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS": 4,
        "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS": 5,
        "GUAC_ADMIN_USER": "admin",
        "GUAC_ADMIN_PASS": "password",
        "GUAC_API_URL": "https://guac",
        "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS": 3,
        "GUACAMOLE_HISTORY_LOOKBACK_SECONDS": 30,
        "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS": 300,
        "logging": "logger",
    }

    runtime = create_session_observation_runtime(providers)
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


def test_session_observation_runtime_resolves_mutable_callbacks_at_service_creation():
    captured = []

    class FakeSessionObservations:
        def __init__(self, **kwargs):
            captured.append(kwargs["retry_delay"])

    providers = {
        "SessionObservations": FakeSessionObservations,
        "DB_ENGINE": None,
        "GUACAMOLE_DB_ENGINE": None,
        "_encrypt_runtime_secret": lambda value: value,
        "_decrypt_runtime_secret": lambda value: value,
        "requests": SimpleNamespace(get=None, post=None, delete=None),
        "text": None,
        "IntegrityError": RuntimeError,
        "enqueue_session_observation": lambda _payload: False,
        "session_observation_retry_delay_seconds": lambda _attempts: 1,
        "to_utc": lambda value: value,
        "datetime": SimpleNamespace(now=lambda timezone: timezone),
        "timezone": SimpleNamespace(utc="UTC"),
        "time": SimpleNamespace(time=lambda: 0),
        "ACCESS_AUDIT_URL": "",
        "SESSION_OBSERVER_GATEWAY_ID": "",
        "SESSION_OBSERVER_SIGNING_SECRET": "",
        "SESSION_OBSERVATION_OUTBOX_ENABLED": False,
        "SESSION_OBSERVATION_OUTBOX_BATCH_SIZE": 0,
        "SESSION_OBSERVATION_OUTBOX_MAX_ATTEMPTS": 0,
        "SESSION_OBSERVATION_OUTBOX_REQUEST_TIMEOUT_SECONDS": 0,
        "GUAC_ADMIN_USER": "",
        "GUAC_ADMIN_PASS": "",
        "GUAC_API_URL": "",
        "GUAC_TOKEN_REVOCATION_MAX_ATTEMPTS": 0,
        "GUACAMOLE_HISTORY_LOOKBACK_SECONDS": 0,
        "GUACAMOLE_HISTORY_RECONCILIATION_RETENTION_SECONDS": 0,
        "logging": None,
    }
    runtime = create_session_observation_runtime(providers)
    providers["session_observation_retry_delay_seconds"] = lambda _attempts: 9

    runtime.create_service()
    assert captured[0](1) == 9


def test_session_observation_runtime_forwards_service_facades_dynamically():
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
    providers = {
        "_session_observations_service": lambda: service,
        "_default_retry_delay_seconds_impl": lambda attempts: attempts + 1,
        "_encrypt_secret_impl": lambda value, **kwargs: f"enc:{value}",
        "_decrypt_secret_impl": lambda value, **kwargs: f"dec:{value}",
        "_load_fernet": lambda: "fernet",
    }
    runtime = create_session_observation_runtime(providers)

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
