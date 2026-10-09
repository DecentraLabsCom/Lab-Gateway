"""Application lifespan orchestration for the Gateway FMU facade."""

from contextlib import asynccontextmanager
from typing import Any


def create_lifespan(*, preload_jwks: Any, get_realtime_manager: Any) -> Any:
    """Start the remote WebSocket proxy and stop it cleanly at shutdown."""

    @asynccontextmanager
    async def lifespan(_app):
        manager: Any = None
        manager_started = False
        try:
            await preload_jwks()
            manager = get_realtime_manager()
            if manager is not None:
                manager_started = True
                await manager.start()
            yield
        finally:
            if manager_started and manager is not None:
                await manager.stop()

    return lifespan


__all__ = ["create_lifespan"]
