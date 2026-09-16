from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from worker_compatibility_context import WorkerCompatibilityContext
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


def _context(*, hosts, calls, automator):
    registry = {"value": hosts}
    context = WorkerCompatibilityContext(
        get_is_lite_gateway_impl=lambda: lambda environ: environ["mode"] == "lite",
        get_environ=lambda: {"mode": "lite"},
        get_datetime=lambda: SimpleNamespace(
            now=lambda timezone: ("now", timezone)
        ),
        get_timezone=lambda: SimpleNamespace(utc="UTC"),
        get_hosts=lambda: registry["value"],
        get_jsonify=lambda: lambda payload: ("json", payload),
        get_hosts_lock=lambda: _Lock(calls),
        get_replace_host_registry_impl=lambda: lambda received, **kwargs: calls.append(
            ("replace", received, kwargs)
        ),
        get_reservation_automator=lambda: automator,
        set_host_registry=lambda received: registry.__setitem__("value", received),
    )
    return context, registry


def test_worker_compatibility_runtime_preserves_composition_helpers():
    calls = []
    hosts = {"station-01": {"name": "station-01"}}
    automator = SimpleNamespace(registry="old")
    context, registry = _context(hosts=hosts, calls=calls, automator=automator)
    runtime = create_worker_compatibility_runtime(context)

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

    runtime.replace_host_registry({"station-02": {"name": "station-02"}})
    assert calls[0] == "lock-enter"
    assert calls[1][0:2] == (
        "replace",
        {"station-02": {"name": "station-02"}},
    )
    assert calls[1][2]["reservation_automator"] is automator
    calls[1][2]["set_registry"]({"station-03": {"name": "station-03"}})
    assert registry["value"] == {"station-03": {"name": "station-03"}}
    assert calls[2] == "lock-exit"


def test_worker_compatibility_runtime_publishes_registry_and_resolves_hosts_lazily():
    calls = []
    hosts = {}
    context, registry = _context(
        hosts=hosts,
        calls=calls,
        automator=SimpleNamespace(registry=None),
    )
    runtime = create_worker_compatibility_runtime(context)

    runtime.set_host_registry({"station": {"name": "station"}})

    assert registry["value"] == {"station": {"name": "station"}}


def test_worker_compatibility_context_is_immutable():
    context, _registry = _context(hosts={}, calls=[], automator=SimpleNamespace())

    with pytest.raises(FrozenInstanceError):
        setattr(context, "get_environ", lambda: {})
