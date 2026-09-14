from types import SimpleNamespace

from guacamole_runtime import GuacamoleRuntime, create_guacamole_runtime


def test_guacamole_runtime_forwards_catalog_auth_and_selector_dependencies():
    providers = {
        "_load_guacamole_connections_impl": lambda engine, **kwargs: ([], "not configured"),
        "GUACAMOLE_DB_ENGINE": None,
        "text": "sql-text",
        "logging": SimpleNamespace(),
        "request": SimpleNamespace(headers={"X-Token": "secret"}),
        "_check_guacamole_provisioner_auth_impl": lambda headers, **kwargs: (
            headers,
            kwargs,
        ),
        "GUACAMOLE_PROVISIONER_TOKEN": "secret",
        "GUACAMOLE_PROVISIONER_TOKEN_HEADER": "X-Token",
        "jsonify": "jsonify",
        "_parse_guacamole_selector_impl": lambda value, **kwargs: (value, kwargs),
        "GUAC_SELECTOR_RE": "pattern",
        "_safe_connection_response_impl": lambda value: {"id": value["id"]},
    }
    runtime = create_guacamole_runtime(providers)

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
    assert runtime.parse_guacamole_selector("guac:id:42") == ("guac:id:42", {"selector_pattern": "pattern"})
    assert runtime.safe_connection_response({"id": 42}) == {"id": 42}


def test_guacamole_runtime_keeps_provisioning_callbacks_dynamic():
    providers = {
        "_provision_guacamole_user_impl": lambda *args, **kwargs: kwargs[
            "parse_selector"
        ]("selector"),
        "GUACAMOLE_DB_ENGINE": "engine",
        "parse_guacamole_selector": lambda value: "first",
        "resolve_guacamole_connection": lambda value: {"id": 1},
        "safe_connection_response": lambda value: {"id": value["id"]},
        "text": "sql-text",
        "datetime": SimpleNamespace(fromtimestamp=lambda *args, **kwargs: SimpleNamespace(date=lambda: "date")),
        "timezone": SimpleNamespace(utc="utc"),
        "logging": SimpleNamespace(info=lambda *args: None),
        "_delete_guacamole_user_impl": lambda session_id, **kwargs: kwargs["engine"],
        "_cleanup_guacamole_users_impl": lambda **kwargs: kwargs["engine"],
    }
    runtime = create_guacamole_runtime(providers)

    assert runtime.provision_guacamole_temporary_user("selector", "session", None) == "first"
    providers["parse_guacamole_selector"] = lambda value: "second"
    assert runtime.provision_guacamole_temporary_user("selector", "session", None) == "second"
    assert runtime.delete_guacamole_temporary_user("session") == "engine"
    assert runtime.cleanup_expired_guacamole_temp_users() == "engine"
