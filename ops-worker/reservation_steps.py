"""Physical reservation steps with explicit transport and persistence ports."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional, Tuple

from wol_defaults import DEFAULT_WOL_ATTEMPTS, DEFAULT_WOL_PING_TIMEOUT_SECONDS


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

    attempts = int(
        options.get("attempts", host.get("wake_attempts", DEFAULT_WOL_ATTEMPTS))
    )
    wait_seconds = float(
        options.get("ping_timeout", DEFAULT_WOL_PING_TIMEOUT_SECONDS)
    )
    broadcast = options.get("broadcast") or host.get("broadcast")
    port = int(options.get("port", host.get("wol_port", 9)))
    management = host.get("management") if isinstance(host.get("management"), Mapping) else {}
    configured_probe_port = management.get("port", host.get("management_port", host.get("winrm_port")))
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
    dispatcher_request: Optional[Mapping[str, Any]] = None,
    dispatcher_request_error: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    start = current_epoch()
    success = False
    exit_code = 2
    outcome = "failure"
    result: Dict[str, Any] = {}
    message = ""
    try:
        if dispatcher_request_error:
            result = {"error": dispatcher_request_error, "exitCode": 2, "outcome": "failure"}
            raise ValueError("authoritative Station lease context is unavailable")
        if dispatcher_request is not None:
            result = run_labstation_command(
                host,
                command,
                args,
                None,
                None,
                None,
                None,
                None,
                dispatcher_request=dispatcher_request,
            )
        else:
            result = run_labstation_command(host, command, args, None, None, None, None, None)
        if not isinstance(result, Mapping):
            raise ValueError("Station returned a malformed result")
        raw_exit_code = result.get("exitCode", result.get("exit_code"))
        if type(raw_exit_code) is not int or raw_exit_code < 0:
            raise ValueError("Station returned a malformed result")
        exit_code = raw_exit_code
        success = exit_code < 2
        outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
        message = "Station command {} (exit code {})".format(outcome, exit_code)
    except Exception:
        logger.exception("Lab Station command failed for %s", host.get("name"))
        message = dispatcher_request_error or "Lab Station returned an invalid command result"
        result = {"error": message, "exitCode": 2, "outcome": "failure", "metadata": {}}
        exit_code = 2
        success = False
        outcome = "failure"
    duration_ms = result.get("durationMs", result.get("duration_ms", int((current_epoch() - start) * 1000)))
    status = "completed" if success and exit_code == 0 else "warning" if success else "failed"
    management = host.get("management") if isinstance(host.get("management"), Mapping) else {}
    contract = host.get("contract") if isinstance(host.get("contract"), Mapping) else {}
    summarized = {
        "exitCode": result.get("exitCode", result.get("exit_code")),
        "outcome": result.get("outcome", outcome),
        "platform": host.get("platform", "windows"),
        "transport": result.get("transport", management.get("transport", "winrm")),
        "contractVersion": result.get("contractVersion", str(contract.get("major") or 2) + ".0.0"),
        "stdout": (result.get("stdout") or "").strip(),
        "stderr": (result.get("stderr") or "").strip(),
        "args": args,
        "durationMs": duration_ms,
        "metadata": dict(result.get("metadata") or {}) if isinstance(result.get("metadata"), Mapping) else {},
    }
    record_operation(
        reservation_id,
        lab_id,
        host.get("name", ""),
        action,
        status,
        success,
        response_code=result.get("exitCode", result.get("exit_code")),
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
