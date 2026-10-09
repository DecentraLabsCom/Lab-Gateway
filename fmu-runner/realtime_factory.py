"""Composition of the remote FMU Executor realtime proxy."""

from typing import Any

from station_ws_proxy import StationRealtimeWsProxyManager


def build_realtime_manager(
    *,
    backend: Any,
    logger: Any,
    verify_jwt_token: Any,
    enforce_fmu_claim: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    coerce_epoch_seconds: Any,
    redeem_session_ticket: Any,
    issue_session_ticket: Any,
    confirm_session_started: Any,
    ws_cleanup_seconds: float,
    internal_ws_token: str,
    ws_create_rate_limit_per_minute: int,
    station_manager_factory: Any = StationRealtimeWsProxyManager,
    unsupported_manager_factory: Any,
) -> Any:
    """Proxy realtime sessions to the configured Station or Executor service."""
    if backend.mode == "station":
        return station_manager_factory(
            logger=logger,
            station_backend=backend,
            verify_jwt_token=verify_jwt_token,
            enforce_fmu_claim=enforce_fmu_claim,
            get_claim_lab_id=get_claim_lab_id,
            normalize_lab_id=normalize_lab_id,
            coerce_epoch_seconds=coerce_epoch_seconds,
            redeem_session_ticket=redeem_session_ticket,
            issue_session_ticket=issue_session_ticket,
            confirm_session_started=confirm_session_started,
            ws_cleanup_seconds=ws_cleanup_seconds,
            internal_ws_token=internal_ws_token,
            ws_create_rate_limit_per_minute=ws_create_rate_limit_per_minute,
        )

    return unsupported_manager_factory(
        reason=f"Realtime FMU sessions require a remote Executor; mode is {backend.mode}.",
    )


__all__ = ["build_realtime_manager"]
