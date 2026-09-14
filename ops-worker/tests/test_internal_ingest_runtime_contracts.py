from types import SimpleNamespace

from internal_ingest_runtime import (
    InternalIngestRuntime,
    create_internal_ingest_runtime,
)


def test_internal_ingest_runtime_preserves_payload_auth_and_enqueue_contracts():
    calls = []

    def handle(payload, **kwargs):
        calls.append((payload, kwargs))
        return "response"

    providers = {
        "_handle_internal_ingest_impl": handle,
        "request": SimpleNamespace(
            get_json=lambda silent: {"id": 1},
            headers={"X-Gateway-Observation-Token": "provided"},
        ),
        "SESSION_OBSERVATION_INGEST_TOKEN": "secret",
        "hmac": SimpleNamespace(compare_digest=lambda provided, expected: (provided, expected)),
        "jsonify": "jsonify",
        "enqueue_guacamole_token_revocation": lambda payload: ("revocation", payload),
        "enqueue_session_observation": lambda payload: ("observation", payload),
    }
    runtime = create_internal_ingest_runtime(providers)

    assert isinstance(runtime, InternalIngestRuntime)
    assert runtime.ingest_guacamole_token_revocation() == "response"
    assert runtime.ingest_session_observation() == "response"

    assert calls == [
        (
            {"id": 1},
            {
                "headers": {"X-Gateway-Observation-Token": "provided"},
                "ingest_token": "secret",
                "compare_digest": providers["hmac"].compare_digest,
                "enqueue": providers["enqueue_guacamole_token_revocation"],
                "disabled_error": "Guacamole revocation ingestion is disabled",
                "invalid_error": "invalid or unavailable revocation",
                "jsonify": "jsonify",
            },
        ),
        (
            {"id": 1},
            {
                "headers": {"X-Gateway-Observation-Token": "provided"},
                "ingest_token": "secret",
                "compare_digest": providers["hmac"].compare_digest,
                "enqueue": providers["enqueue_session_observation"],
                "disabled_error": "session observation ingestion is disabled",
                "invalid_error": "invalid or unavailable observation",
                "jsonify": "jsonify",
            },
        ),
    ]


def test_internal_ingest_runtime_resolves_request_and_enqueue_providers_lazily():
    calls = []
    providers = {
        "_handle_internal_ingest_impl": lambda payload, **kwargs: calls.append(
            (payload, kwargs["enqueue"])
        ),
        "request": SimpleNamespace(get_json=lambda silent: {"version": 1}, headers={}),
        "SESSION_OBSERVATION_INGEST_TOKEN": "secret",
        "hmac": SimpleNamespace(compare_digest=lambda *_args: True),
        "jsonify": "jsonify",
        "enqueue_guacamole_token_revocation": "first",
        "enqueue_session_observation": "observation",
    }
    runtime = create_internal_ingest_runtime(providers)
    providers["request"] = SimpleNamespace(get_json=lambda silent: {"version": 2}, headers={})
    providers["enqueue_guacamole_token_revocation"] = "second"

    runtime.ingest_guacamole_token_revocation()

    assert calls == [({"version": 2}, "second")]
