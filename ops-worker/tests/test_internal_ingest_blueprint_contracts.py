import hmac

from flask import Flask

import worker
from internal_ingest_blueprint import create_internal_ingest_blueprint


def _register(app, *, token=lambda: "gateway-token", revocation=None, observation=None):
    app.register_blueprint(
        create_internal_ingest_blueprint(
            ingest_token=token,
            compare_digest=hmac.compare_digest,
            enqueue_revocation=revocation or (lambda _payload: True),
            enqueue_observation=observation or (lambda _payload: True),
        )
    )


def test_internal_ingest_blueprint_preserves_both_authenticated_ingestion_contracts():
    app = Flask("internal-ingest-blueprint-contract")
    calls = []
    _register(
        app,
        revocation=lambda payload: calls.append(("revocation", payload)) or True,
        observation=lambda payload: calls.append(("observation", payload)) or True,
    )

    rules = {
        rule.rule: (rule.endpoint, rule.methods)
        for rule in app.url_map.iter_rules()
        if rule.rule in {
            "/internal/guacamole-token-revocations",
            "/internal/session-observations",
        }
    }
    assert rules == {
        "/internal/guacamole-token-revocations": (
            "internal_ingest.ingest_guacamole_token_revocation",
            {"POST", "OPTIONS"},
        ),
        "/internal/session-observations": (
            "internal_ingest.ingest_session_observation",
            {"POST", "OPTIONS"},
        ),
    }

    headers = {"X-Gateway-Observation-Token": "gateway-token"}
    revocation_payload = {"authToken": "secret-token"}
    observation_payload = {"dedupKey": "a" * 64}
    revocation = app.test_client().post(
        "/internal/guacamole-token-revocations",
        json=revocation_payload,
        headers=headers,
    )
    observation = app.test_client().post(
        "/internal/session-observations",
        json=observation_payload,
        headers=headers,
    )

    assert revocation.status_code == 202
    assert revocation.get_json() == {"accepted": True}
    assert observation.status_code == 202
    assert observation.get_json() == {"accepted": True}
    assert calls == [
        ("revocation", revocation_payload),
        ("observation", observation_payload),
    ]
    assert "secret-token" not in revocation.get_data(as_text=True)


def test_internal_ingest_blueprint_preserves_auth_and_disabled_errors_for_both_routes():
    app = Flask("internal-ingest-errors-blueprint-contract")
    _register(app, token=lambda: "")
    disabled = app.test_client().post(
        "/internal/guacamole-token-revocations",
        json={"authToken": "secret-token"},
    )
    assert disabled.status_code == 503
    assert disabled.get_json() == {
        "accepted": False,
        "error": "Guacamole revocation ingestion is disabled",
    }

    app = Flask("internal-ingest-auth-blueprint-contract")
    _register(app)
    unauthorized = app.test_client().post(
        "/internal/session-observations",
        json={"dedupKey": "a" * 64},
        headers={"X-Gateway-Observation-Token": "wrong-token"},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.get_json() == {"accepted": False, "error": "unauthorized"}


def test_worker_internal_ingest_blueprint_resolves_runtime_token_and_queues(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "SESSION_OBSERVATION_INGEST_TOKEN", "runtime-token")
    monkeypatch.setattr(
        worker,
        "enqueue_session_observation",
        lambda payload: calls.append(payload) or True,
    )

    response = worker.APP.test_client().post(
        "/internal/session-observations",
        json={"dedupKey": "b" * 64},
        headers={"X-Gateway-Observation-Token": "runtime-token"},
    )

    assert response.status_code == 202
    assert response.json == {"accepted": True}
    assert calls == [{"dedupKey": "b" * 64}]
