"""Demo lifecycle operations with explicit application dependencies."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


DemoContext = Dict[str, Any]


def build_demo_context(
    payload: Dict[str, Any],
    *,
    operation_id_pattern: Any,
    canonical_lab_id: Callable[[Any], Optional[str]],
    configured_lab_id: Any,
    find_host_by_lab: Callable[[str], Optional[Mapping[str, Any]]],
    db_engine: Any,
) -> Tuple[Optional[DemoContext], Optional[str]]:
    demo_id = str(payload.get("demoId") or "").strip()
    if not operation_id_pattern.fullmatch(demo_id):
        return None, "demoId must be an operational identifier in the form demo:<jti>"

    lab_id = canonical_lab_id(payload.get("labId"))
    if lab_id is None:
        return None, "labId must be a decimal identifier"
    expected_lab_id = canonical_lab_id(configured_lab_id)
    if expected_lab_id is None or expected_lab_id != lab_id:
        return None, "labId does not match the configured demo binding"

    host = find_host_by_lab(lab_id)
    if not host:
        return None, "no Lab Station host is bound to the demo laboratory"

    if not db_engine:
        return None, "demo lifecycle persistence is unavailable"

    return {
        "demo_id": demo_id,
        "lab_id": lab_id,
        "host": host,
    }, None


def operation_completed(
    demo_id: str,
    action: str,
    *,
    db_engine: Any,
    sql_text: Callable[[str], Any],
    logger: Any,
) -> bool:
    if not db_engine:
        return False
    try:
        with db_engine.connect() as conn:
            return conn.execute(
                sql_text(
                    "SELECT 1 FROM reservation_operations "
                    "WHERE reservation_id=:reservation_id AND action=:action "
                    "AND success=1 ORDER BY id DESC LIMIT 1"
                ),
                {"reservation_id": demo_id, "action": action},
            ).first() is not None
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Demo lifecycle idempotency check failed: %s", type(exc).__name__)
        return False


def record_demo_event(
    context: DemoContext,
    event: str,
    success: bool,
    *,
    event_actions: Mapping[str, str],
    record_operation: Callable[..., Any],
    payload: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    action = "demo_cleanup" if event == "cleanup" else event_actions.get(event)
    if not action:
        raise ValueError("unsupported demo lifecycle event")
    record_operation(
        reservation_id=context["demo_id"],
        lab_id=context["lab_id"],
        host_name=context["host"].get("name", ""),
        action=action,
        status="completed" if success else "failed",
        success=success,
        response_code=200 if success else 502,
        payload=payload,
        message=message,
    )


def host_is_ready(
    host: Mapping[str, Any],
    *,
    db_engine: Any,
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Mapping[str, Any]]],
    to_utc: Callable[[Any], Optional[datetime]],
    max_age_seconds: int,
    now: Callable[[], datetime],
    logger: Any,
) -> bool:
    if not db_engine:
        return False
    try:
        with db_engine.connect() as conn:
            heartbeat = fetch_latest_heartbeat(conn, host.get("name", ""))
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Unable to inspect demo Station heartbeat: %s", type(exc).__name__)
        return False
    if not heartbeat or heartbeat.get("localMode") or heartbeat.get("localSession"):
        return False
    heartbeat_ts = to_utc(heartbeat.get("timestamp"))
    if not heartbeat_ts:
        return False
    age = (now() - heartbeat_ts).total_seconds()
    return heartbeat.get("ready") is True and 0 <= age <= max_age_seconds


def handle_demo_start(
    payload: Dict[str, Any],
    *,
    get_context: Callable[[Dict[str, Any]], Tuple[Optional[DemoContext], Optional[str]]],
    operation_completed: Callable[[str, str], bool],
    parse_bool: Callable[[Any, bool], bool],
    host_is_ready: Callable[[Mapping[str, Any]], bool],
    reservation_start: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], int]],
    reservation_end: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], int]],
    record_event: Callable[..., Any],
) -> Tuple[Dict[str, Any], int]:
    context, error = get_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None

    demo_id = context["demo_id"]
    if operation_completed(demo_id, "demo_cleanup"):
        return {"success": False, "error": "demo operation has already been cleaned up"}, 409
    if operation_completed(demo_id, "demo_start"):
        return {
            "success": True,
            "alreadyStarted": True,
            "operationId": demo_id,
            "labId": context["lab_id"],
            "host": context["host"].get("name"),
            "steps": [],
        }, 200

    requested_wake = parse_bool(payload.get("wake", True), True)
    wake = requested_wake and not host_is_ready(context["host"])
    guard_grace = payload.get("guardGrace", 30)
    try:
        guard_grace = max(0, min(600, int(guard_grace)))
    except (TypeError, ValueError):
        return {"success": False, "error": "guardGrace must be an integer between 0 and 600"}, 400

    reservation_response, reservation_status = reservation_start(
        {
            "reservationId": demo_id,
            "host": context["host"].get("name"),
            "labId": context["lab_id"],
            "wake": wake,
            "wakeOptions": payload.get("wakeOptions") or {},
            "prepare": True,
            "prepareArgs": [
                f"--guard-grace={guard_grace}",
                "--guard-message=Demo access preparation",
            ],
            "guardGrace": guard_grace,
            "power": payload.get("power", True),
            "actor": "demo-lifecycle",
        }
    )
    started = reservation_response.get("success") is True
    record_event(
        context,
        "start",
        started,
        payload={"phase": "start", "steps": reservation_response.get("steps", [])},
        message=None if started else "Demo physical preparation failed",
    )
    if not started:
        cleanup_response, cleanup_status = handle_demo_end(
            {
                "demoId": demo_id,
                "labId": context["lab_id"],
                "reason": "failed",
            },
            get_context=get_context,
            operation_completed=operation_completed,
            reservation_end=reservation_end,
            record_event=record_event,
        )
        reservation_response["cleanup"] = cleanup_response
        if cleanup_status >= 500:
            reservation_status = cleanup_status
        return {
            "success": False,
            "operationId": demo_id,
            "labId": context["lab_id"],
            "host": context["host"].get("name"),
            "steps": reservation_response.get("steps", []),
            "cleanup": cleanup_response,
        }, reservation_status

    return {
        "success": True,
        "operationId": demo_id,
        "labId": context["lab_id"],
        "host": context["host"].get("name"),
        "prepared": True,
        "steps": reservation_response.get("steps", []),
    }, 200


def handle_demo_event(
    payload: Dict[str, Any],
    *,
    get_context: Callable[[Dict[str, Any]], Tuple[Optional[DemoContext], Optional[str]]],
    operation_completed: Callable[[str, str], bool],
    record_event: Callable[..., Any],
    event_actions: Mapping[str, str],
) -> Tuple[Dict[str, Any], int]:
    context, error = get_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None
    event = str(payload.get("event") or "").strip().lower()
    if event not in {"connected", "expired", "failed", "disconnected"}:
        return {"success": False, "error": "unsupported demo lifecycle event"}, 400
    if not operation_completed(context["demo_id"], "demo_start"):
        return {"success": False, "error": "demo physical preparation has not completed"}, 409
    action = event_actions[event]
    if operation_completed(context["demo_id"], action):
        return {"success": True, "alreadyRecorded": True, "operationId": context["demo_id"]}, 200
    record_event(context, event, True, payload={"event": event})
    return {"success": True, "operationId": context["demo_id"], "event": event}, 200


def handle_demo_end(
    payload: Dict[str, Any],
    *,
    get_context: Callable[[Dict[str, Any]], Tuple[Optional[DemoContext], Optional[str]]],
    operation_completed: Callable[[str, str], bool],
    reservation_end: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], int]],
    record_event: Callable[..., Any],
) -> Tuple[Dict[str, Any], int]:
    context, error = get_context(payload)
    if error:
        return {"success": False, "error": error}, 400
    assert context is not None
    demo_id = context["demo_id"]
    if operation_completed(demo_id, "demo_cleanup"):
        return {"success": True, "alreadyReleased": True, "operationId": demo_id}, 200

    reason = str(payload.get("reason") or "disconnected").strip().lower()
    if reason not in {"expired", "failed", "disconnected"}:
        return {"success": False, "error": "reason must be expired, failed or disconnected"}, 400
    reason_action = {
        "expired": "demo_expiry",
        "failed": "demo_failure",
        "disconnected": "demo_disconnect",
    }[reason]
    if not operation_completed(demo_id, reason_action):
        record_event(context, reason, True, payload={"reason": reason})

    reservation_response, reservation_status = reservation_end(
        {
            "reservationId": demo_id,
            "host": context["host"].get("name"),
            "labId": context["lab_id"],
            "release": True,
            "releaseArgs": ["--reboot"],
            "power": payload.get("power", True),
            "actor": "demo-lifecycle",
        }
    )
    released = reservation_response.get("success") is True
    record_event(
        context,
        "cleanup",
        released,
        payload={"reason": reason, "steps": reservation_response.get("steps", [])},
        message=None if released else "Demo physical cleanup failed",
    )
    return {
        "success": released,
        "operationId": demo_id,
        "labId": context["lab_id"],
        "host": context["host"].get("name"),
        "steps": reservation_response.get("steps", []),
    }, reservation_status if not released else 200


__all__ = [
    "build_demo_context",
    "handle_demo_end",
    "handle_demo_event",
    "handle_demo_start",
    "host_is_ready",
    "operation_completed",
    "record_demo_event",
]
