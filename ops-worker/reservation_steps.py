"""Physical reservation steps with explicit transport and persistence ports."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional, Tuple


def perform_wake_step(
    host: Mapping[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    options: Mapping[str, Any],
    *,
    wol_and_wait: Callable[..., Tuple[bool, int]],
    record_operation: Callable[..., Any],
    notify_failure: Callable[..., Any],
    current_epoch: Callable[[], float],
    logger: Any,
) -> Tuple[bool, Dict[str, Any]]:
    mac = options.get("mac") or host.get("mac")
    if not mac:
        message = "MAC address not configured"
        record_operation(
            reservation_id,
            lab_id,
            host.get("name", ""),
            "wake",
            "failed",
            False,
            message=message,
        )
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {},
        }

    ping_target = options.get("ping_target") or host.get("ping_target") or host.get("address")
    if not ping_target:
        message = "Ping target not configured"
        record_operation(
            reservation_id,
            lab_id,
            host.get("name", ""),
            "wake",
            "failed",
            False,
            message=message,
        )
        return False, {
            "action": "wake",
            "success": False,
            "status": "failed",
            "message": message,
            "details": {},
        }

    attempts = int(options.get("attempts", host.get("wake_attempts", 3)))
    wait_seconds = float(options.get("ping_timeout", 10))
    broadcast = options.get("broadcast") or host.get("broadcast")
    port = int(options.get("port", host.get("wol_port", 9)))
    configured_probe_port = host.get("winrm_port")
    try:
        probe_port = int(configured_probe_port) if configured_probe_port not in (None, "") else None
    except (TypeError, ValueError):
        probe_port = None

    start = current_epoch()
    success = False
    used_attempts = 0
    message = ""
    try:
        success, used_attempts = wol_and_wait(
            mac,
            broadcast,
            port,
            ping_target,
            attempts,
            wait_seconds,
            probe_port=probe_port,
        )
        message = "Host reachable" if success else "Host did not respond to ping"
    except Exception:
        logger.exception("Wake operation failed for %s", host.get("name"))
        message = "Wake operation failed"
    duration_ms = int((current_epoch() - start) * 1000)
    status = "completed" if success else "failed"
    details = {
        "mac": mac,
        "pingTarget": ping_target,
        "attemptsRequested": attempts,
        "attemptsUsed": used_attempts,
        "waitSeconds": wait_seconds,
        "port": port,
        "broadcast": broadcast,
    }
    record_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        "wake",
        status,
        success,
        response_code=200 if success else 504,
        duration_ms=duration_ms,
        payload=details,
        message=message,
    )
    if not success:
        notify_failure(reservation_id, lab_id, host.get("name", ""), "wake", message, details)
    return success, {
        "action": "wake",
        "success": success,
        "status": status,
        "message": message,
        "durationMs": duration_ms,
        "details": details,
    }


def perform_command_step(
    host: Mapping[str, Any],
    reservation_id: str,
    lab_id: Optional[str],
    action: str,
    command: str,
    args: List[str],
    *,
    run_labstation_command: Callable[..., Dict[str, Any]],
    record_operation: Callable[..., Any],
    notify_failure: Callable[..., Any],
    current_epoch: Callable[[], float],
    logger: Any,
) -> Tuple[bool, Dict[str, Any]]:
    start = current_epoch()
    success = False
    result: Dict[str, Any] = {}
    message = ""
    try:
        result = run_labstation_command(host, command, args, None, None, None, None, None)
        success = result.get("exit_code", 1) == 0
        message = "Exit code {}".format(result.get("exit_code"))
    except Exception:
        logger.exception("Lab Station command failed for %s", host.get("name"))
        message = "Lab Station command failed"
        result = {"error": message}
    duration_ms = result.get("duration_ms", int((current_epoch() - start) * 1000))
    status = "completed" if success else "failed"
    summarized = {
        "exitCode": result.get("exit_code"),
        "stdout": (result.get("stdout") or "").strip(),
        "stderr": (result.get("stderr") or "").strip(),
        "args": args,
        "durationMs": duration_ms,
    }
    record_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        action,
        status,
        success,
        response_code=result.get("exit_code"),
        duration_ms=duration_ms,
        payload=summarized,
        message=message,
    )
    if not success:
        notify_failure(reservation_id, lab_id, host.get("name", ""), action, message, summarized)
    return success, {
        "action": action,
        "success": success,
        "status": status,
        "message": message,
        "details": summarized,
    }


__all__ = ["perform_command_step", "perform_wake_step"]
