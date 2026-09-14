import inspect
from pathlib import Path

import worker
from runtime_composition import compose_worker_app


def test_worker_does_not_publish_legacy_facades():
    facade_names = (
        "api_wol",
        "api_winrm",
        "api_poll_heartbeat",
        "api_stream_heartbeat",
        "api_reservation_start",
        "api_reservation_end",
        "api_demo_start",
        "api_demo_event",
        "api_demo_end",
        "api_reservation_timeline",
        "api_hosts_inventory",
        "api_internal_guacamole_connections",
        "api_internal_guacamole_provision",
        "api_internal_guacamole_delete",
        "api_hosts_discover",
        "api_hosts_provision",
        "api_hosts_update",
        "api_preview_winrm_trust",
        "api_get_winrm_trust",
        "api_save_winrm_trust",
        "api_delete_winrm_trust",
        "api_save_winrm_credentials",
        "api_hosts_reload",
        "api_aas_sync",
        "api_hosts_local_mode",
        "api_operations_recent",
        "api_aas_sync_lab",
        "health",
    )

    assert all(not hasattr(worker, name) for name in facade_names)
    source = Path(worker.__file__).read_text(encoding="utf-8")
    assert "legacy_api" not in source
    assert "_LEGACY_API" not in source
    assert "create_legacy_api" not in source


def test_compose_worker_app_builds_context_then_registers_blueprints():
    events = []
    providers = {"runtime": "live"}
    app = object()
    context = {"runtime": "live"}

    result = compose_worker_app(
        app,
        providers,
        context_factory=lambda values: events.append(("context", values)) or context,
        register_blueprints=lambda current_app, current: events.append(
            ("blueprints", current_app, current, dict(providers))
        ),
    )

    assert result is context
    assert [event[0] for event in events] == ["context", "blueprints"]
    assert events[-1][3] == {"runtime": "live"}


def test_compose_worker_app_has_no_legacy_factory_parameter():
    assert "legacy_factory" not in inspect.signature(compose_worker_app).parameters
