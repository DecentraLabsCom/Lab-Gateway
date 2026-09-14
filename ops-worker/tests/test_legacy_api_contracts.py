from flask import Flask, jsonify

import worker
from legacy_api import LEGACY_API_NAMES, create_legacy_api


def test_legacy_api_factory_keeps_the_full_compatibility_surface():
    facades = create_legacy_api({})

    assert tuple(facades) == LEGACY_API_NAMES
    assert all(callable(facades[name]) for name in LEGACY_API_NAMES)
    assert all(callable(getattr(worker, name)) for name in LEGACY_API_NAMES)


def test_legacy_api_facades_resolve_mutable_providers_at_call_time():
    app = Flask(__name__)
    state = {"reload_hosts": lambda: (3, None)}
    facades = create_legacy_api(
        {
            "reload_hosts": lambda: state["reload_hosts"](),
            "jsonify": jsonify,
        }
    )

    with app.test_request_context("/api/hosts/reload"):
        assert facades["api_hosts_reload"]().json == {"reloaded": True, "hosts": 3}

    state["reload_hosts"] = lambda: (0, "catalog unavailable")
    with app.test_request_context("/api/hosts/reload"):
        response, status = facades["api_hosts_reload"]()
        assert status == 500
        assert response.json == {"error": "Hosts configuration reload failed"}


def test_worker_reexports_legacy_facades_without_defining_routes_or_handlers():
    source = open(worker.__file__, encoding="utf-8").read()

    assert "def api_" not in source
    assert "def health(" not in source
    assert "APP.register_blueprint(" not in source
    assert "create_legacy_api" in source
