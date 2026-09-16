from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from app_hooks_context import AppHooksContext
from app_hooks_runtime import AppHooksRuntime, create_app_hooks_runtime


def _context(**overrides):
    values = {
        "get_env_or_secret_file_impl": lambda: lambda name, default, **kwargs: (
            f"{name}:{default}"
        ),
        "get_logger": lambda: SimpleNamespace(exception=lambda *args: None),
        "get_sanitize_log_value_impl": lambda: lambda value: f"safe:{value}",
        "get_as_utc_datetime_impl": lambda: lambda value, **kwargs: (value, kwargs),
        "get_datetime": lambda: SimpleNamespace(fromisoformat="fromisoformat"),
        "get_timezone": lambda: SimpleNamespace(utc="UTC"),
        "get_request_headers": lambda: {"id": "42", "X-Ops-Token": "secret"},
        "get_request_path": lambda: "/api/hosts",
        "get_request_id_from_headers_impl": lambda: lambda headers: (
            f"request:{headers.get('id')}"
        ),
        "get_internal_error_response_impl": lambda: lambda *args, **kwargs: (
            "error-response",
            kwargs["status"],
        ),
        "get_request_id": lambda: lambda: "request:42",
        "get_sanitize_log_value": lambda: lambda value: f"safe:{value}",
        "get_handle_unexpected_exception_impl": lambda: lambda exc, **kwargs: None,
        "get_internal_error_response": lambda: lambda *args, **kwargs: (
            "internal",
            args,
            kwargs,
        ),
        "get_requires_ops_internal_auth_impl": lambda: lambda path: path.startswith(
            "/api/"
        ),
        "get_check_ops_internal_auth_impl": lambda: lambda **kwargs: None,
        "get_ops_internal_auth_header": lambda: "X-Ops-Token",
        "get_ops_internal_auth_token": lambda: "secret",
        "get_requires_ops_internal_auth": lambda: lambda path: True,
        "get_jsonify": lambda: "jsonify",
    }
    values.update(overrides)
    return AppHooksContext(**values)


def test_app_hooks_runtime_forwards_explicit_security_and_error_dependencies():
    runtime = create_app_hooks_runtime(_context())

    assert isinstance(runtime, AppHooksRuntime)
    assert runtime.env_or_secret_file("NAME", "default") == "NAME:default"
    assert runtime.sanitize_log_value("value") == "safe:value"
    utc_timestamp = runtime.as_utc_datetime("timestamp")
    assert utc_timestamp is not None
    assert utc_timestamp[0] == "timestamp"
    reservation_timestamp = runtime.parse_reservation_datetime("timestamp")
    assert reservation_timestamp is not None
    assert reservation_timestamp[0] == "timestamp"
    assert runtime.request_id() == "request:42"
    assert runtime.internal_error_response(
        "context",
        RuntimeError("failure"),
        status=503,
    ) == ("error-response", 503)
    assert runtime.requires_ops_internal_auth("/api/hosts") is True
    assert runtime.require_ops_internal_auth() is None


def test_app_hooks_runtime_resolves_mutable_request_callbacks():
    request = {"headers": {"id": "first", "X-Token": "secret"}, "path": "/api"}
    context = _context(
        get_request_headers=lambda: request["headers"],
        get_request_path=lambda: request["path"],
        get_request_id_from_headers_impl=lambda: lambda headers: headers.get(
            "id", "missing"
        ),
        get_ops_internal_auth_header=lambda: "X-Token",
        get_check_ops_internal_auth_impl=lambda: lambda **kwargs: kwargs["provided"],
    )
    runtime = create_app_hooks_runtime(context)

    assert runtime.request_id() == "first"
    assert runtime.require_ops_internal_auth() == "secret"
    request = {"headers": {"id": "second", "X-Token": "new"}, "path": "/api"}

    assert runtime.request_id() == "second"
    assert runtime.require_ops_internal_auth() == "new"


def test_app_hooks_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "get_jsonify", lambda: "changed")
