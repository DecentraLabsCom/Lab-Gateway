"""Application lifespan orchestration for the FMU Runner."""

from contextlib import asynccontextmanager
from typing import Any


def create_lifespan(
    *,
    initialize_runtime: Any = None,
    init_db: Any,
    preload_jwks: Any,
    get_realtime_manager: Any,
    get_executor: Any,
    shutdown_executor: Any,
    cleanup_temp_files: Any,
) -> Any:
    """Build the lifespan while keeping resource effects explicitly injected."""

    @asynccontextmanager
    async def lifespan(_app):
        manager = None
        manager_started = False
        try:
            if initialize_runtime is not None:
                await initialize_runtime()
            await init_db()
            await preload_jwks()
            manager = get_realtime_manager()
            if manager is not None:
                manager_started = True
                await manager.start()
            yield
        finally:
            try:
                if manager_started:
                    await manager.stop()
            finally:
                try:
                    shutdown_executor(get_executor())
                finally:
                    await cleanup_temp_files()

    return lifespan


__all__ = ["create_lifespan"]
