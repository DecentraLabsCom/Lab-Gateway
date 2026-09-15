from dataclasses import FrozenInstanceError

import pytest

from host_reload_context import HostReloadContext
from host_reload_runtime import HostReloadRuntime, create_host_reload_runtime


def _context(**overrides):
    values = {
        "reload_hosts": lambda **kwargs: (3, None),
        "load_config": lambda: {},
        "registry_factory": lambda config: config,
        "refresh_trust_store": lambda hosts: None,
        "replace_registry": lambda registry: None,
        "get_logger": lambda: "logger",
    }
    values.update(overrides)
    return HostReloadContext(**values)


def test_host_reload_runtime_forwards_explicit_reload_dependencies_and_result():
    calls = []
    context = _context(
        reload_hosts=lambda **kwargs: calls.append(kwargs) or (3, None),
        load_config="load",
        registry_factory="registry",
        refresh_trust_store="refresh",
        replace_registry="replace",
        get_logger=lambda: "logger",
    )
    runtime = create_host_reload_runtime(context)

    assert isinstance(runtime, HostReloadRuntime)
    assert runtime.reload_hosts() == (3, None)
    assert calls == [{
        "load_config": "load",
        "registry_factory": "registry",
        "refresh_trust_store": "refresh",
        "replace_registry": "replace",
        "logger": "logger",
    }]


def test_host_reload_runtime_resolves_mutable_callbacks_at_call_time():
    reload_hosts = lambda **_kwargs: (1, None)
    context = _context(reload_hosts=lambda **kwargs: reload_hosts(**kwargs))
    runtime = create_host_reload_runtime(context)
    reload_hosts = lambda **_kwargs: (2, None)

    assert runtime.reload_hosts() == (2, None)


def test_host_reload_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.load_config = "changed"
