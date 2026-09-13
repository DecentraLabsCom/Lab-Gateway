"""Composition of the local, Station and unsupported realtime managers."""

from typing import Any

from realtime_ws import RealtimeWsManager
from station_ws_proxy import StationRealtimeWsProxyManager


def build_realtime_manager(
    *,
    backend: Any,
    local_realtime_enabled: bool,
    logger: Any,
    verify_jwt_token: Any,
    enforce_fmu_claim: Any,
    resolve_fmu_path: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    coerce_epoch_seconds: Any,
    acquire_slot: Any,
    release_slot: Any,
    redeem_session_ticket: Any,
    issue_session_ticket: Any,
    confirm_session_started: Any,
    ws_session_queue_size: int,
    ws_heartbeat_seconds: float,
    ws_expiring_notice_seconds: int,
    ws_attach_grace_seconds: int,
    ws_cleanup_seconds: float,
    internal_ws_token: str,
    ws_create_rate_limit_per_minute: int,
    local_manager_factory: Any = RealtimeWsManager,
    station_manager_factory: Any = StationRealtimeWsProxyManager,
    unsupported_manager_factory: Any,
) -> Any:
    """Select and construct the realtime manager for the active FMU backend."""
    if backend.supports_local_execution and local_realtime_enabled:
        return local_manager_factory(
            logger=logger,
            verify_jwt_token=verify_jwt_token,
            enforce_fmu_claim=enforce_fmu_claim,
            resolve_fmu_path=resolve_fmu_path,
            get_claim_lab_id=get_claim_lab_id,
            normalize_lab_id=normalize_lab_id,
            coerce_epoch_seconds=coerce_epoch_seconds,
            acquire_slot=acquire_slot,
            release_slot=release_slot,
            redeem_session_ticket=redeem_session_ticket,
            issue_session_ticket=issue_session_ticket,
            confirm_session_started=confirm_session_started,
            ws_session_queue_size=ws_session_queue_size,
            ws_heartbeat_seconds=ws_heartbeat_seconds,
            ws_expiring_notice_seconds=ws_expiring_notice_seconds,
            ws_attach_grace_seconds=ws_attach_grace_seconds,
            ws_cleanup_seconds=ws_cleanup_seconds,
            internal_ws_token=internal_ws_token,
            ws_create_rate_limit_per_minute=ws_create_rate_limit_per_minute,
        )

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

    reason = (
        "Local realtime FMU execution is disabled by default because native "
        "doStep calls cannot be force-terminated inside the ASGI process. "
        "Use FMU_BACKEND_MODE=station in production, or explicitly set "
        "FMU_LOCAL_REALTIME_ENABLED=true only for isolated development."
        if backend.supports_local_execution
        else None
    )
    return unsupported_manager_factory(reason=reason)


__all__ = ["build_realtime_manager"]
