from host_inventory_runtime import HostInventoryRuntime, create_host_inventory_runtime


def test_host_inventory_runtime_forwards_public_projection_dependencies():
    calls = []
    providers = {
        "_safe_host_inventory_entry_impl": lambda host, **kwargs: calls.append(
            ("safe", host, kwargs)
        ) or {"name": host["name"]},
        "credential_ref_for_host": lambda host: "credential",
        "inspect_winrm_trust": lambda host: {"status": "ready"},
        "winrm_credentials_configured": lambda ref: True,
        "_build_host_inventory_from_sources_impl": lambda registry, **kwargs: calls.append(
            ("inventory", registry, kwargs)
        ) or {"hosts": []},
        "HOSTS": "registry",
        "HOSTS_LOCK": "lock",
        "load_dynamic_config": lambda: {"hosts": []},
        "load_guacamole_connections": lambda: ([], None),
        "normalize_match_key": lambda value: str(value or "").lower(),
        "safe_host_inventory_entry": lambda host, **kwargs: {"name": host["name"]},
    }
    runtime = create_host_inventory_runtime(providers)

    assert isinstance(runtime, HostInventoryRuntime)
    assert runtime.safe_host_inventory_entry({"name": "station"}) == {"name": "station"}
    assert runtime.build_host_inventory() == {"hosts": []}
    assert calls[0][0] == "safe"
    assert calls[1][0] == "inventory"


def test_host_inventory_runtime_resolves_mutable_inventory_sources():
    providers = {
        "_build_host_inventory_from_sources_impl": lambda registry, **kwargs: kwargs[
            "load_dynamic_config"
        ](),
        "HOSTS": "registry",
        "HOSTS_LOCK": "lock",
        "load_dynamic_config": lambda: {"version": "first"},
        "load_guacamole_connections": lambda: ([], None),
        "normalize_match_key": lambda value: str(value or "").lower(),
        "safe_host_inventory_entry": lambda host, **kwargs: {},
    }
    runtime = create_host_inventory_runtime(providers)

    assert runtime.build_host_inventory() == {"version": "first"}
    providers["load_dynamic_config"] = lambda: {"version": "second"}
    assert runtime.build_host_inventory() == {"version": "second"}
