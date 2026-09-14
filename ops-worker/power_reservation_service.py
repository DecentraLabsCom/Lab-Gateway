"""Power policy integration for reservation lifecycle operations."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional


def project_power_operation(
    operation: Mapping[str, Any],
    *,
    record_operation: Callable[..., Any],
    logger: Any,
) -> None:
    """Project a power step into the existing reservation timeline."""
    reservation_id = str(operation.get("reservationId") or "").strip()
    controller_id = str(operation.get("controllerId") or "").strip()
    action = str(operation.get("action") or "").strip().lower()
    if not reservation_id or not controller_id or action not in {"on", "off", "cycle"}:
        logger.warning("Skipping malformed power operation projection")
        return
    status = str(operation.get("status") or "failed")
    success = bool(operation.get("success"))
    record_operation(
        reservation_id=reservation_id,
        lab_id=str(operation.get("labId")) if operation.get("labId") is not None else None,
        host_name=controller_id,
        action=f"power:{action}",
        status=status,
        success=success,
        response_code=200 if success else 502,
        duration_ms=operation.get("durationMs"),
        payload={
            "phase": operation.get("phase"),
            "controllerId": controller_id,
            "outlet": operation.get("outlet"),
            "idempotencyKey": operation.get("idempotencyKey"),
            "observedStateBefore": operation.get("observedStateBefore"),
            "observedStateAfter": operation.get("observedStateAfter"),
            "actor": operation.get("actor"),
            "reason": operation.get("reason"),
        },
        message=operation.get("message"),
    )


def host_local_mode_enabled(
    host: Mapping[str, Any],
    *,
    db_engine: Any,
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Mapping[str, Any]]],
    parse_bool: Callable[[Any, bool], bool],
    logger: Any,
) -> bool:
    """Read the last persisted Lab Station local-mode signal when available."""
    if db_engine:
        try:
            with db_engine.connect() as conn:
                heartbeat = fetch_latest_heartbeat(conn, host.get("name", ""))
            if heartbeat is not None:
                return bool(heartbeat.get("localMode"))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Unable to read local mode for power policy: %s", type(exc).__name__)
    return parse_bool(host.get("local_mode", host.get("localMode")), False)


def execute_reservation_power_phase(
    reservation_id: str,
    lab_id: Optional[str],
    host: Mapping[str, Any],
    phase: str,
    payload: Dict[str, Any],
    *,
    parse_bool: Callable[[Any, bool], bool],
    power_runtime: Any,
    power_validation_error_type: type[BaseException],
    host_local_mode: Callable[[Mapping[str, Any]], bool],
    logger: Any,
) -> Dict[str, Any]:
    if not lab_id or not parse_bool(payload.get("power", True), True):
        return {"success": True, "status": "power_disabled", "phase": phase, "steps": []}
    try:
        return power_runtime.execute_policy(
            str(lab_id),
            str(reservation_id),
            phase,
            actor=str(payload.get("actor") or "reservation-orchestrator"),
            local_mode=host_local_mode(host),
        )
    except (power_validation_error_type, KeyError, PermissionError) as exc:
        logger.warning("Power policy phase failed: %s", type(exc).__name__)
        return {
            "success": False,
            "status": "failed",
            "phase": phase,
            "steps": [],
            "message": "Power policy phase failed",
        }


__all__ = [
    "execute_reservation_power_phase",
    "host_local_mode_enabled",
    "project_power_operation",
]
