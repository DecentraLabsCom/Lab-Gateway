import asyncio
from concurrent.futures import ProcessPoolExecutor

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from execution_lifecycle import (
    create_simulation_executor,
    preload_jwks_if_enabled,
    shutdown_simulation_executor,
    submit_simulation,
)


def _fake_process_pool(shutdown_calls):
    executor = object.__new__(ProcessPoolExecutor)
    setattr(executor, "shutdown", lambda **kwargs: shutdown_calls.append(kwargs))
    return executor


def test_shutdown_simulation_executor_ignores_non_process_executors():
    shutdown_simulation_executor(object())


def test_shutdown_simulation_executor_closes_process_pool_without_force():
    shutdown_calls = []
    executor = _fake_process_pool(shutdown_calls)

    shutdown_simulation_executor(executor)

    assert shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_shutdown_simulation_executor_kills_live_workers_when_forced():
    killed = []
    shutdown_calls = []

    class FakeProcess:
        def is_alive(self):
            return True

        def kill(self):
            killed.append(True)

    executor = _fake_process_pool(shutdown_calls)
    setattr(executor, "_processes", {1: FakeProcess()})

    shutdown_simulation_executor(executor, force=True)

    assert killed == [True]
    assert shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_create_simulation_executor_uses_four_workers(monkeypatch):
    created = []

    class FakeExecutor:
        def __init__(self, *, max_workers):
            created.append(max_workers)

    monkeypatch.setattr("execution_lifecycle.ProcessPoolExecutor", FakeExecutor)

    executor = create_simulation_executor()

    assert isinstance(executor, FakeExecutor)
    assert created == [4]


def test_create_simulation_executor_fails_closed_when_pool_is_unavailable(monkeypatch):
    class UnavailableExecutor:
        def __init__(self, **_kwargs):
            raise PermissionError("not allowed")

    class FakeLogger:
        def __init__(self):
            self.errors = []

        def error(self, message, error):
            self.errors.append((message, error))

    fake_logger = FakeLogger()
    monkeypatch.setattr("execution_lifecycle.ProcessPoolExecutor", UnavailableExecutor)

    assert create_simulation_executor(logger=fake_logger) is None
    assert fake_logger.errors[0][0] == (
        "ProcessPoolExecutor unavailable; local FMU execution disabled: %s"
    )


def test_submit_simulation_rejects_missing_configured_executor():
    try:
        submit_simulation(None, object(), lambda *_args, **_kwargs: None, "arg")
    except RuntimeError as error:
        assert str(error) == "isolated FMU worker pool is unavailable"
    else:
        raise AssertionError("Expected missing executor to fail closed")


def test_submit_simulation_uses_lightweight_test_executor():
    calls = []

    class FakeExecutor:
        def submit(self, runner, *args):
            calls.append((runner, args))
            return "future"

    runner = object()
    executor = FakeExecutor()

    result = submit_simulation(executor, runner, lambda *_args, **_kwargs: None, "arg", 2)

    assert result == (executor, "future")
    assert calls == [(runner, ("arg", 2))]


def test_submit_simulation_creates_one_process_pool_for_production(monkeypatch):
    created = []

    class FakeExecutor:
        def __init__(self, *, max_workers=None):
            self.calls = []
            created.append((self, max_workers))

        def submit(self, runner, *args):
            self.calls.append((runner, args))
            return "future"

    monkeypatch.setattr("execution_lifecycle.ProcessPoolExecutor", FakeExecutor)
    configured_executor = FakeExecutor(max_workers=4)
    runner = object()

    result = submit_simulation(configured_executor, runner, lambda *_args, **_kwargs: None, "arg")

    worker_executor, future = result
    assert worker_executor is not configured_executor
    assert future == "future"
    assert created[-1][1] == 1
    assert worker_executor.calls == [(runner, ("arg",))]


def test_submit_simulation_forces_shutdown_when_worker_submit_fails(monkeypatch):
    shutdown_calls = []

    class FakeExecutor:
        def __init__(self, **_kwargs):
            pass

        def submit(self, *_args):
            raise RuntimeError("submit failed")

    monkeypatch.setattr("execution_lifecycle.ProcessPoolExecutor", FakeExecutor)

    with pytest.raises(RuntimeError, match="submit failed"):
        submit_simulation(
            FakeExecutor(),
            object(),
            lambda executor, *, force: shutdown_calls.append((executor, force)),
            "arg",
        )

    assert shutdown_calls[0][1] is True


def test_preload_jwks_if_enabled_skips_disabled_fetch():
    fetch_jwks = AsyncMock()

    assert asyncio.run(
        preload_jwks_if_enabled(fetch_jwks=fetch_jwks, enabled=False)
    ) is False

    fetch_jwks.assert_not_awaited()


def test_preload_jwks_if_enabled_fetches_with_force():
    fetch_jwks = AsyncMock()

    assert asyncio.run(
        preload_jwks_if_enabled(fetch_jwks=fetch_jwks, enabled=True)
    ) is True

    fetch_jwks.assert_awaited_once_with(force=True)


def test_preload_jwks_if_enabled_logs_and_continues_on_http_error(caplog):
    fetch_jwks = AsyncMock(side_effect=HTTPException(status_code=503))

    assert asyncio.run(
        preload_jwks_if_enabled(fetch_jwks=fetch_jwks, enabled=True)
    ) is False

    assert "JWKS preload failed" in caplog.text