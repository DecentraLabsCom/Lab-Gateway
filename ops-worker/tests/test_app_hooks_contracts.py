from flask import Flask, abort, jsonify

import app_hooks
import worker


def _build_app(*, token="gateway-token", header="X-Ops-Internal-Token"):
    app = Flask(__name__)
    state = {"token": token, "header": header}

    app_hooks.register_app_hooks(
        app,
        internal_error_response=lambda context, exc: (
            jsonify({"context": context, "error": type(exc).__name__}),
            599,
        ),
        internal_auth_token=lambda: state["token"],
        internal_auth_header=lambda: state["header"],
        requires_internal_auth=lambda path: path.startswith("/api/"),
    )

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/value")
    def value():
        return jsonify({"value": 42})

    @app.get("/api/failure")
    def failure():
        raise RuntimeError("secret")

    @app.get("/api/not-found")
    def not_found():
        abort(404)

    return app, state


def test_app_hooks_request_id_and_log_sanitizer_preserve_bounded_contracts():
    assert app_hooks.sanitize_log_value("bad\r\nvalue") == "bad\\r\\nvalue"
    assert app_hooks.request_id_from_headers(
        {"X-Request-ID": "request-123"},
        request_id_factory=lambda: "generated",
    ) == "request-123"
    assert app_hooks.request_id_from_headers(
        {"X-Request-ID": "bad value"},
        request_id_factory=lambda: "generated",
    ) == "generated"


def test_app_hooks_internal_auth_path_policy_preserves_public_boundaries():
    assert app_hooks.requires_ops_internal_auth("/api/hosts") is True
    assert app_hooks.requires_ops_internal_auth("/aas-admin/lab/lab-1/sync") is True
    assert app_hooks.requires_ops_internal_auth("/health") is False
    assert app_hooks.requires_ops_internal_auth("/api") is False


def test_app_hooks_keep_health_public_and_gate_ops_api():
    app, state = _build_app()
    client = app.test_client()

    assert client.get("/health").status_code == 200
    assert client.get("/api/value").status_code == 401
    assert client.get("/api/value", headers={state["header"]: state["token"]}).status_code == 200


def test_app_hooks_read_auth_providers_for_each_request():
    app, state = _build_app()
    client = app.test_client()

    state["token"] = "rotated-token"
    state["header"] = "X-Rotated-Token"

    assert client.get("/api/value", headers={"X-Ops-Internal-Token": "gateway-token"}).status_code == 401
    assert client.get("/api/value", headers={"X-Rotated-Token": "rotated-token"}).status_code == 200


def test_app_hooks_delegate_unexpected_errors_and_preserve_http_errors():
    app, state = _build_app()
    client = app.test_client()
    headers = {state["header"]: state["token"]}

    failure = client.get("/api/failure", headers=headers)
    assert failure.status_code == 599
    assert failure.json == {"context": "Unhandled Ops Worker request", "error": "RuntimeError"}

    not_found = client.get("/api/not-found", headers=headers)
    assert not_found.status_code == 404


def test_worker_keeps_hook_facades_and_moves_decorators_to_composition_module():
    source = open(worker.__file__, encoding="utf-8").read()

    assert callable(worker.handle_unexpected_exception)
    assert callable(worker.require_ops_internal_auth)
    assert "@APP.errorhandler(Exception)" not in source
    assert "@APP.before_request" not in source


def test_worker_auth_facade_keeps_the_public_health_contract():
    with worker.APP.test_request_context("/health"):
        assert worker.require_ops_internal_auth() is None


def test_internal_error_response_contract_keeps_public_payload_and_sanitizes_context():
    calls = []

    with worker.APP.test_request_context("/health"):
        response, status = app_hooks.internal_error_response(
            "bad\r\nforged",
            RuntimeError("secret details"),
            request_id=lambda: "request-123",
            sanitize_log_value=lambda value: str(value).replace("\r", "\\r").replace("\n", "\\n"),
            log_exception=lambda message, context: calls.append((message, context)),
            jsonify=jsonify,
        )

    assert status == 500
    assert response.get_json() == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "request-123",
    }
    assert calls == [("Ops Worker request failed context=%s", "bad\\r\\nforged")]
