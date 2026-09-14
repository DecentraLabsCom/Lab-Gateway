from types import SimpleNamespace

from app_hooks_runtime import AppHooksRuntime, create_app_hooks_runtime


def test_app_hooks_runtime_forwards_secret_time_request_and_error_dependencies():
    calls = []
    providers = {
        "_env_or_secret_file_impl": lambda name, default, **kwargs: f"{name}:{default}",
        "logging": SimpleNamespace(exception=lambda *args: calls.append(("exception", args))),
        "_sanitize_log_value_impl": lambda value: f"safe:{value}",
        "_sanitize_log_value": lambda value: f"safe:{value}",
        "_as_utc_datetime_impl": lambda value, **kwargs: (value, kwargs),
        "datetime": SimpleNamespace(fromisoformat="fromisoformat"),
        "timezone": SimpleNamespace(utc="UTC"),
        "_request_id_from_headers_impl": lambda headers: f"request:{headers.get('id')}",
        "_request_id": lambda: "request:42",
        "request": SimpleNamespace(headers={"id": "42"}, path="/api/hosts"),
        "_internal_error_response_impl": lambda *args, **kwargs: calls.append(
            ("error", args, kwargs)
        ) or ("error-response", kwargs["status"]),
        "jsonify": "jsonify",
        "_handle_unexpected_exception_impl": lambda exc, **kwargs: None,
        "_requires_ops_internal_auth_impl": lambda path: path.startswith("/api/"),
        "_check_ops_internal_auth_impl": lambda **kwargs: calls.append(
            ("auth", kwargs)
        ) or None,
        "OPS_INTERNAL_AUTH_HEADER": "X-Ops-Token",
        "OPS_INTERNAL_AUTH_TOKEN": "secret",
        "internal_error_response": lambda *args, **kwargs: ("internal", args, kwargs),
        "_requires_ops_internal_auth": lambda path: True,
    }
    runtime = create_app_hooks_runtime(providers)

    assert isinstance(runtime, AppHooksRuntime)
    assert runtime.env_or_secret_file("NAME", "default") == "NAME:default"
    assert runtime.sanitize_log_value("value") == "safe:value"
    assert runtime.as_utc_datetime("timestamp")[0] == "timestamp"
    assert runtime.parse_reservation_datetime("timestamp")[0] == "timestamp"
    assert runtime.request_id() == "request:42"
    assert runtime.internal_error_response("context", RuntimeError("failure"), status=503) == (
        "error-response",
        503,
    )
    assert runtime.requires_ops_internal_auth("/api/hosts") is True
    assert runtime.require_ops_internal_auth() is None
    assert any(call[0] == "auth" for call in calls)


def test_app_hooks_runtime_resolves_mutable_auth_and_request_callbacks():
    providers = {
        "_request_id_from_headers_impl": lambda headers: headers.get("id", "first"),
        "request": SimpleNamespace(headers={"id": "first"}, path="/api"),
        "_requires_ops_internal_auth_impl": lambda path: path == "/api",
        "_requires_ops_internal_auth": lambda path: path == "/api",
        "_check_ops_internal_auth_impl": lambda **kwargs: kwargs["provided"],
        "OPS_INTERNAL_AUTH_HEADER": "X-Token",
        "OPS_INTERNAL_AUTH_TOKEN": "secret",
    }
    runtime = create_app_hooks_runtime(providers)

    assert runtime.request_id() == "first"
    assert runtime.require_ops_internal_auth() == ""
    providers["request"] = SimpleNamespace(headers={"X-Token": "secret", "id": "second"}, path="/api")
    assert runtime.request_id() == "second"
    assert runtime.require_ops_internal_auth() == "secret"
