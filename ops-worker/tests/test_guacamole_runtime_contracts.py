from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from guacamole_context import GuacamoleContext
from guacamole_runtime import GuacamoleRuntime, create_guacamole_runtime


def _context(**overrides):
    values = {
        "get_load_connections_impl": lambda: lambda engine, **kwargs: (
            [],
            "not configured",
        ),
        "get_db_engine": lambda: None,
        "get_sql_text": lambda: "sql-text",
        "get_logger": lambda: SimpleNamespace(),
        "get_request_headers": lambda: {"X-Token": "secret"},
        "get_check_auth_impl": lambda: lambda headers, **kwargs: (headers, kwargs),
        "get_expected_token": lambda: "secret",
        "get_token_header": lambda: "X-Token",
        "get_jsonify": lambda: "jsonify",
        "get_parse_selector_impl": lambda: lambda value, **kwargs: (value, kwargs),
        "get_selector_pattern": lambda: "pattern",
        "get_safe_connection_response_impl": lambda: lambda value: {
            "id": value["id"]
        },
        "get_provision_impl": lambda: lambda *args, **kwargs: kwargs[
            "parse_selector"
        ]("selector"),
        "get_parse_selector": lambda: lambda value: "first",
        "get_resolve_connection": lambda: lambda value: {"id": 1},
        "get_safe_connection_response": lambda: lambda value: {"id": value["id"]},
        "get_datetime": lambda: SimpleNamespace(
            fromtimestamp=lambda *args, **kwargs: SimpleNamespace(
                date=lambda: "date"
            )
        ),
        "get_timezone": lambda: SimpleNamespace(utc="utc"),
        "get_delete_impl": lambda: lambda session_id, **kwargs: kwargs["engine"],
        "get_cleanup_impl": lambda: lambda **kwargs: kwargs["engine"],
    }
    values.update(overrides)
    return GuacamoleContext(**values)


def test_guacamole_runtime_forwards_catalog_auth_and_selector_dependencies():
    context = _context()
    runtime = create_guacamole_runtime(context)

    assert isinstance(runtime, GuacamoleRuntime)
    assert runtime.load_guacamole_connections() == ([], "not configured")
    assert runtime.require_guacamole_provisioner_auth() == (
        {"X-Token": "secret"},
        {
            "expected_token": "secret",
            "token_header": "X-Token",
            "jsonify": "jsonify",
        },
    )
    assert runtime.parse_guacamole_selector("guac:id:42") == (
        "guac:id:42",
        {"selector_pattern": "pattern"},
    )
    assert runtime.safe_connection_response({"id": 42}) == {"id": 42}


def test_guacamole_runtime_keeps_provisioning_callbacks_dynamic():
    parse_selector = lambda _value: "first"
    context = _context(get_parse_selector=lambda: parse_selector)
    runtime = create_guacamole_runtime(context)

    assert runtime.provision_guacamole_temporary_user("selector", "session", None) == "first"
    parse_selector = lambda _value: "second"
    assert runtime.provision_guacamole_temporary_user("selector", "session", None) == "second"
    assert runtime.delete_guacamole_temporary_user("session") is None
    assert runtime.cleanup_expired_guacamole_temp_users() is None


def test_guacamole_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_db_engine = lambda: "changed"
