from dataclasses import FrozenInstanceError

import pytest

from entrypoint_context import EntrypointContext
from entrypoint_runtime import EntrypointRuntime, create_entrypoint_runtime


def _context(**overrides):
    values = {
        "get_configure_logging_impl": lambda: lambda **kwargs: None,
        "get_log_level": lambda: "debug",
        "get_basic_config": lambda: "basic-config",
        "get_run_impl": lambda: lambda **kwargs: None,
        "get_configure_logging": lambda: "configure",
        "get_refresh_trust_store": lambda: "refresh",
        "get_hosts": lambda: [{"name": "station-01"}],
        "get_start_scheduler": lambda: "scheduler",
        "get_bind": lambda: "127.0.0.1",
        "get_port": lambda: 9876,
        "get_serve": lambda: "serve",
        "get_app": lambda: "app",
    }
    values.update(overrides)
    return EntrypointContext(**values)


def test_entrypoint_runtime_forwards_logging_and_process_providers():
    calls = []
    context = _context(
        get_configure_logging_impl=lambda: lambda **kwargs: calls.append(("logging", kwargs)),
        get_run_impl=lambda: lambda **kwargs: calls.append(("run", kwargs)),
    )
    runtime = create_entrypoint_runtime(context)

    assert isinstance(runtime, EntrypointRuntime)
    assert runtime.configure_logging() is None
    assert runtime.main() is None
    assert calls == [
        (
            "logging",
            {"level": "debug", "basic_config": "basic-config"},
        ),
        (
            "run",
            {
                "configure_logging": "configure",
                "refresh_trust_store": "refresh",
                "hosts": [{"name": "station-01"}],
                "start_scheduler": "scheduler",
                "bind": "127.0.0.1",
                "port": 9876,
                "serve": "serve",
                "app": "app",
            },
        ),
    ]


def test_entrypoint_runtime_resolves_live_startup_configuration():
    port = 8081
    calls = []
    context = _context(
        get_port=lambda: port,
        get_run_impl=lambda: lambda **kwargs: calls.append(kwargs),
    )
    runtime = create_entrypoint_runtime(context)
    port = 9090

    runtime.main()

    assert calls[0]["port"] == 9090


def test_entrypoint_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "get_app", lambda: "changed")
