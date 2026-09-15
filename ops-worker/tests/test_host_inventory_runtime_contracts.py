import host_inventory_runtime
from host_inventory_context import HostInventoryContext
from host_inventory_runtime import HostInventoryRuntime, create_host_inventory_runtime


def test_host_inventory_runtime_uses_explicit_context_dependencies(monkeypatch):
    calls = []
    context = HostInventoryContext(
        get_host_registry=lambda: "registry",
        get_hosts_lock=lambda: "lock",
        load_dynamic_config=lambda: {"hosts": []},
        load_guacamole_connections=lambda: ([], None),
        normalize_match_key=lambda value: str(value or "").lower(),
        credential_ref_for_host=lambda host: "credential",
        inspect_winrm_trust=lambda host: {"status": "ready"},
        winrm_credentials_configured=lambda ref: True,
    )

    def build_inventory(registry, **kwargs):
        calls.append(("inventory", registry, kwargs))
        return {"hosts": []}

    monkeypatch.setattr(host_inventory_runtime, "build_host_inventory_from_sources", build_inventory)
    runtime = create_host_inventory_runtime(context)

    assert isinstance(runtime, HostInventoryRuntime)
    assert runtime.safe_host_inventory_entry({"name": "station"})["credentialRef"] == "credential"
    assert runtime.build_host_inventory() == {"hosts": []}
    assert calls == [
        (
            "inventory",
            "registry",
            {
                "hosts_lock": "lock",
                "load_dynamic_config": context.load_dynamic_config,
                "load_guacamole_connections": context.load_guacamole_connections,
                "normalize_key": context.normalize_match_key,
                "safe_entry": runtime.safe_host_inventory_entry,
            },
        )
    ]


def test_host_inventory_context_is_immutable():
    context = HostInventoryContext(
        get_host_registry=lambda: "registry",
        get_hosts_lock=lambda: "lock",
        load_dynamic_config=lambda: {"hosts": []},
        load_guacamole_connections=lambda: ([], None),
        normalize_match_key=lambda value: str(value or "").lower(),
        credential_ref_for_host=lambda host: "credential",
        inspect_winrm_trust=lambda host: {},
        winrm_credentials_configured=lambda ref: False,
    )

    try:
        context.get_host_registry = lambda: "replacement"
    except AttributeError:
        pass
    else:
        raise AssertionError("HostInventoryContext must be immutable")
