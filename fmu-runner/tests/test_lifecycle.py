import asyncio

import pytest

from lifecycle import create_lifespan


def test_lifecycle_starts_and_stops_remote_realtime_manager():
    events = []

    class Manager:
        async def start(self):
            events.append("manager.start")

        async def stop(self):
            events.append("manager.stop")

    async def preload_jwks():
        events.append("preload_jwks")

    lifespan = create_lifespan(
        preload_jwks=preload_jwks,
        get_realtime_manager=lambda: Manager(),
    )

    async def exercise():
        async with lifespan(object()):
            events.append("ready")

    asyncio.run(exercise())

    assert events == ["preload_jwks", "manager.start", "ready", "manager.stop"]


def test_lifecycle_skips_optional_realtime_manager():
    events = []

    async def preload_jwks():
        events.append("preload_jwks")

    lifespan = create_lifespan(
        preload_jwks=preload_jwks,
        get_realtime_manager=lambda: None,
    )

    async def exercise():
        async with lifespan(object()):
            events.append("ready")

    asyncio.run(exercise())

    assert events == ["preload_jwks", "ready"]


def test_lifecycle_does_not_start_manager_when_jwks_preload_fails():
    async def preload_jwks():
        raise RuntimeError("JWKS unavailable")

    # No manager should be requested after a failed startup prerequisite.
    lifespan = create_lifespan(
        preload_jwks=preload_jwks,
        get_realtime_manager=lambda: (_ for _ in ()).throw(AssertionError("manager requested")),
    )

    async def exercise():
        with pytest.raises(RuntimeError, match="JWKS unavailable"):
            async with lifespan(object()):
                raise AssertionError("application entered lifespan")

    asyncio.run(exercise())
