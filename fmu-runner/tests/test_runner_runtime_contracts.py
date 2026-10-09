from pathlib import Path

import pytest

from runner_runtime import create_fmu_runner_runtime


def test_runtime_owns_only_observation_proxy_and_remote_service_state():
    runtime = create_fmu_runner_runtime()

    assert runtime.backend is None
    assert runtime.realtime_manager is None
    assert runtime.observed_credentials == set()
    assert runtime.proxy_download_hits == {}
    assert not hasattr(runtime, "executor")
    assert not hasattr(runtime, "history_db_path")


def test_runtime_binds_backend_and_realtime_once():
    runtime = create_fmu_runner_runtime()
    backend = object()
    realtime = object()

    runtime.bind_backend(backend)
    runtime.bind_realtime_manager(realtime)

    assert runtime.backend is backend
    assert runtime.realtime_manager is realtime

    with pytest.raises(RuntimeError):
        runtime.bind_backend(object())
    with pytest.raises(RuntimeError):
        runtime.bind_realtime_manager(object())


def test_runtime_state_is_explicit_and_has_no_module_namespace_lookup():
    source = Path(__file__).parents[1].joinpath("runner_runtime.py").read_text(encoding="utf-8")

    assert "globals()" not in source
    assert "Mapping" not in source
