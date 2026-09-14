from types import SimpleNamespace

from worker_compatibility_runtime import (
    WorkerCompatibilityRuntime,
    create_worker_compatibility_runtime,
)


class _Lock:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        self._calls.append("lock-enter")

    def __exit__(self, *_args):
        self._calls.append("lock-exit")


def test_worker_compatibility_runtime_preserves_composition_helpers():
    calls = []
    registry = SimpleNamespace(get=lambda name: {"name": name} if name == "station-01" else None)
    automator = SimpleNamespace(registry="old")
    providers = {
        "_is_lite_gateway_config_impl": lambda environ: environ["mode"] == "lite",
        "os": SimpleNamespace(environ={"mode": "lite"}),
        "datetime": SimpleNamespace(now=lambda timezone: ("now", timezone)),
        "timezone": SimpleNamespace(utc="UTC"),
        "HOSTS": registry,
        "jsonify": lambda payload: ("json", payload),
        "HOSTS_LOCK": _Lock(calls),
        "_replace_host_registry_impl": lambda received, **kwargs: calls.append(
            ("replace", received, kwargs)
        ),
        "RESERVATION_AUTOMATOR": automator,
    }
    providers["_set_host_registry"] = lambda received: providers.__setitem__(
        "HOSTS",
        received,
    )
    runtime = create_worker_compatibility_runtime(providers)

    assert isinstance(runtime, WorkerCompatibilityRuntime)
    assert runtime.is_lite_gateway() is True
    assert runtime.now_utc() == ("now", "UTC")
    assert runtime.winrm_trust_host_or_404("station-01") == (
        {"name": "station-01"},
        None,
    )
    assert runtime.winrm_trust_host_or_404("missing") == (
        None,
        (
            (
                "json",
                {"error": "host 'missing' not found in config"},
            ),
            404,
        ),
    )

    runtime.replace_host_registry("new")
    assert calls[0] == "lock-enter"
    assert calls[1][0:2] == ("replace", "new")
    assert calls[1][2]["reservation_automator"] is automator
    calls[1][2]["set_registry"]("published")
    assert providers["HOSTS"] == "published"
    assert calls[2] == "lock-exit"


def test_worker_compatibility_runtime_publishes_registry_and_resolves_providers_lazily():
    providers = {
        "_is_lite_gateway_config_impl": lambda _environ: False,
        "os": SimpleNamespace(environ={}),
        "datetime": SimpleNamespace(now=lambda timezone: timezone),
        "timezone": SimpleNamespace(utc="UTC"),
        "HOSTS": SimpleNamespace(get=lambda _name: None),
        "jsonify": lambda payload: payload,
        "HOSTS_LOCK": _Lock([]),
        "_replace_host_registry_impl": lambda *_args, **_kwargs: None,
        "RESERVATION_AUTOMATOR": SimpleNamespace(registry=None),
    }
    providers["_set_host_registry"] = lambda received: providers.__setitem__(
        "HOSTS",
        received,
    )
    runtime = create_worker_compatibility_runtime(providers)
    replacement = object()

    runtime.set_host_registry(replacement)

    assert providers["HOSTS"] is replacement
