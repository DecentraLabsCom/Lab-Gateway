import logging
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from fastapi import HTTPException


_logger = logging.getLogger("fmu-runner")


async def preload_jwks_if_enabled(*, fetch_jwks: Any, enabled: bool) -> bool:
    if not enabled:
        return False
    try:
        await fetch_jwks(force=True)
    except HTTPException:
        logging.warning("JWKS preload failed; health will remain DOWN until keys are loaded")
        return False
    return True


def create_simulation_executor(*, logger: Any = None) -> Any:
    try:
        return ProcessPoolExecutor(max_workers=4)
    except (PermissionError, OSError) as exc:
        active_logger = logger or _logger
        active_logger.error("ProcessPoolExecutor unavailable; local FMU execution disabled: %s", exc)
        return None


def submit_simulation(
    configured_executor: Any,
    simulation_runner: Any,
    shutdown_executor: Any,
    *args: Any,
    process_pool_type: Any = None,
    process_pool_factory: Any = None,
) -> tuple[Any, Any]:
    if configured_executor is None:
        raise RuntimeError("isolated FMU worker pool is unavailable")

    pool_type = process_pool_type or ProcessPoolExecutor
    pool_factory = process_pool_factory or ProcessPoolExecutor
    if isinstance(configured_executor, pool_type):
        try:
            executor = pool_factory(max_workers=1)
        except (PermissionError, OSError) as exc:
            raise RuntimeError("isolated FMU worker pool is unavailable") from exc
        try:
            future = executor.submit(simulation_runner, *args)
        except Exception:
            shutdown_executor(executor, force=True)
            raise
        return executor, future
    return configured_executor, configured_executor.submit(simulation_runner, *args)


def shutdown_simulation_executor(executor: Any, *, force: bool = False) -> None:
    """Stop one isolated worker pool, killing native workers on cancellation."""
    if not isinstance(executor, ProcessPoolExecutor):
        return
    if force:
        processes = getattr(executor, "_processes", {}) or {}
        for process in list(processes.values()):
            try:
                if process.is_alive():
                    killer = getattr(process, "kill", None) or process.terminate
                    killer()
            except Exception as exc:
                _logger.warning("Unable to terminate FMU worker process: %s", exc)
    executor.shutdown(wait=False, cancel_futures=True)