from host_reload_runtime import HostReloadRuntime, create_host_reload_runtime


def test_host_reload_runtime_forwards_reload_dependencies_and_result():
    calls = []
    providers = {
        "_reload_hosts_impl": lambda **kwargs: calls.append(kwargs) or (3, None),
        "load_config": "load",
        "HostRegistry": "registry",
        "refresh_winrm_trust_store": "refresh",
        "_replace_host_registry": "replace",
        "logging": "logger",
    }
    runtime = create_host_reload_runtime(providers)

    assert isinstance(runtime, HostReloadRuntime)
    assert runtime.reload_hosts() == (3, None)
    assert calls == [{
        "load_config": "load",
        "registry_factory": "registry",
        "refresh_trust_store": "refresh",
        "replace_registry": "replace",
        "logger": "logger",
    }]
