"""Composition of the local and Station FMU backends."""

from typing import Any

from fmu_backend import LocalFmuBackend, StationFmuBackend


def build_fmu_backend(
    *,
    mode: str,
    local_dev_mode: bool,
    local_executor_base_url: str = "",
    local_executor_internal_token: str = "",
    station_base_url: str,
    station_internal_token: str,
    station_request_timeout: float,
    health_loader: Any,
    model_metadata_loader: Any,
    list_loader: Any,
    logger: Any,
    station_backend_factory: Any = StationFmuBackend,
    local_backend_factory: Any = LocalFmuBackend,
) -> Any:
    """Select the Station service, local Executor service or guarded test backend."""
    if mode == "station":
        logger.info("FMU backend mode selected: station")
        return station_backend_factory(
            base_url=station_base_url,
            internal_token=station_internal_token,
            request_timeout=station_request_timeout,
        )

    if mode == "local" and local_dev_mode and local_executor_base_url:
        logger.info("FMU backend mode selected: local FMU Executor service")
        return station_backend_factory(
            base_url=local_executor_base_url,
            internal_token=local_executor_internal_token,
            request_timeout=station_request_timeout,
        )

    if mode != "local":
        logger.error(
            "Unknown FMU_BACKEND_MODE=%s; local execution remains disabled",
            mode,
        )

    if mode == "local" and not local_dev_mode:
        logger.error(
            "FMU_BACKEND_MODE=local requires FMU_LOCAL_DEV_MODE=true; "
            "native FMU execution is disabled",
        )

    logger.info("FMU backend mode selected: local")
    return local_backend_factory(
        health_loader=health_loader,
        model_metadata_loader=model_metadata_loader,
        list_loader=list_loader,
        allow_execution=mode == "local" and local_dev_mode,
    )


__all__ = ["build_fmu_backend"]
