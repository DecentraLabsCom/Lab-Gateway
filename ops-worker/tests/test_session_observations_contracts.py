import base64
import json
from datetime import datetime, timezone
from unittest.mock import Mock

from session_observations import SessionObservations, default_retry_delay_seconds


def test_default_retry_delay_is_bounded_exponential_and_handles_non_positive_attempts():
    assert default_retry_delay_seconds(0) == 5
    assert default_retry_delay_seconds(1) == 5
    assert default_retry_delay_seconds(3) == 20
    assert default_retry_delay_seconds(99) == 300


def _service(**overrides):
    secret = base64.urlsafe_b64encode(b"a-32-byte-session-observer-secret!!").rstrip(b"=").decode()
    values = {
        "db_engine": None,
        "guacamole_db_engine": None,
        "encrypt_secret": lambda value: f"encrypted:{value}",
        "decrypt_secret": lambda value: str(value).removeprefix("encrypted:"),
        "http_get": Mock(),
        "http_post": Mock(),
        "http_delete": Mock(),
        "sql_text": lambda statement: statement,
        "integrity_error_type": Exception,
        "enqueue_session_observation": Mock(return_value=True),
        "retry_delay": lambda attempts: attempts,
        "to_utc": lambda value: value if isinstance(value, datetime) else None,
        "now": lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        "current_epoch": lambda: 1_000,
        "logger": Mock(),
        "config": {
            "access_audit_url": "https://full.example/audit",
            "session_observer_gateway_id": "gateway-a",
            "session_observer_signing_secret": secret,
            "session_observation_outbox_enabled": True,
            "session_observation_outbox_batch_size": 20,
            "session_observation_outbox_max_attempts": 20,
            "session_observation_outbox_request_timeout_seconds": 5,
            "guac_admin_user": "",
            "guac_admin_pass": "",
            "guac_api_url": "http://guacamole:8080/guacamole/api",
            "guac_token_revocation_max_attempts": 20,
            "guacamole_history_lookback_seconds": 30,
            "guacamole_history_reconciliation_retention_seconds": 300,
        },
    }
    values.update(overrides)
    return SessionObservations(**values)


def test_observer_authorization_is_scoped_and_uses_explicit_clock():
    service = _service()

    authorization = service.session_observer_authorization()

    assert authorization.startswith("Bearer ")
    encoded_payload = authorization.removeprefix("Bearer ").split(".")[1]
    encoded_payload += "=" * (-len(encoded_payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(encoded_payload))
    assert claims["iss"] == "gateway-a"
    assert claims["aud"] == "session-observation"
    assert claims["scope"] == "session-observation:submit"
    assert claims["iat"] == 1_000
    assert claims["exp"] == 1_060


def test_observation_epoch_normalizes_naive_aware_and_invalid_values():
    service = _service()

    assert service.session_observed_epoch(datetime(2026, 1, 1)) == 1_767_225_600
    assert service.session_observed_epoch(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 1_767_225_600
    assert service.session_observed_epoch("invalid") == 1_000


def test_enqueue_observation_fails_closed_without_database():
    service = _service()

    assert service.enqueue_session_observation({}) is False
