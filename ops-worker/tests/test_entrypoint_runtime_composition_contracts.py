from types import SimpleNamespace

from entrypoint_runtime import EntrypointRuntime, create_entrypoint_runtime


def test_entrypoint_runtime_forwards_logging_and_process_providers():
    calls = []
    providers = {
        "_configure_logging_impl": lambda **kwargs: calls.append(("logging", kwargs)),
        "_run_entrypoint_impl": lambda **kwargs: calls.append(("run", kwargs)),
        "os": SimpleNamespace(
            getenv=lambda name, default=None: {
                "OPS_LOG_LEVEL": "debug",
                "OPS_BIND": "127.0.0.1",
                "OPS_PORT": "9876",
            }.get(name, default)
        ),
        "logging": SimpleNamespace(basicConfig="basic-config"),
        "refresh_winrm_trust_store": "refresh",
        "HOSTS": SimpleNamespace(all_hosts=lambda: [{"name": "station-01"}]),
        "start_scheduler": "scheduler",
        "serve": "serve",
        "APP": "app",
        "configure_logging": "configure",
    }
    runtime = create_entrypoint_runtime(providers)

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
