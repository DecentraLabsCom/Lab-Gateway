"""Reservation lifecycle operations with explicit runtime dependencies."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional, Tuple


def handle_reservation_start(
    payload: Dict[str, Any],
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    get_mandatory_field: Callable[..., Optional[str]],
    parse_bool: Callable[[Any, bool], bool],
    execute_power_phase: Callable[[str, Optional[str], Mapping[str, Any], str, Dict[str, Any]], Dict[str, Any]],
    perform_wake_step: Callable[[Mapping[str, Any], str, Optional[str], Dict[str, Any]], Tuple[bool, Dict[str, Any]]],
    perform_command_step: Callable[
        [Mapping[str, Any], str, Optional[str], str, str, List[str]],
        Tuple[bool, Dict[str, Any]],
    ],
    normalize_args: Callable[[Any, Optional[List[str]]], List[str]],
) -> Tuple[Dict[str, Any], int]:
    reservation_id = get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = get_mandatory_field(payload, "host", "hostName")
    lab_id = get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = find_host(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    wake_enabled = parse_bool(payload.get("wake", True), True)
    prepare_enabled = parse_bool(payload.get("prepare", True), True)
    guard_grace = int(payload.get("guardGrace", 90))
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if lab_id:
        power_result = execute_power_phase(
            reservation_id,
            lab_id,
            host,
            "pre_start",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and wake_enabled:
        ok, step = perform_wake_step(
            host,
            reservation_id,
            lab_id,
            payload.get("wakeOptions", {}),
        )
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and lab_id:
        power_result = execute_power_phase(
            reservation_id,
            lab_id,
            host,
            "post_start",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and prepare_enabled:
        prepare_args = normalize_args(
            payload.get("prepareArgs"),
            [f"--guard-grace={guard_grace}"],
        )
        ok, step = perform_command_step(
            host,
            reservation_id,
            lab_id,
            "prepare",
            "prepare-session",
            prepare_args,
        )
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


def handle_reservation_end(
    payload: Dict[str, Any],
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    get_mandatory_field: Callable[..., Optional[str]],
    parse_bool: Callable[[Any, bool], bool],
    execute_power_phase: Callable[[str, Optional[str], Mapping[str, Any], str, Dict[str, Any]], Dict[str, Any]],
    perform_command_step: Callable[
        [Mapping[str, Any], str, Optional[str], str, str, List[str]],
        Tuple[bool, Dict[str, Any]],
    ],
    normalize_args: Callable[[Any, Optional[List[str]]], List[str]],
) -> Tuple[Dict[str, Any], int]:
    reservation_id = get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = get_mandatory_field(payload, "host", "hostName")
    lab_id = get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or not host_name:
        return {"error": "reservationId and host are required"}, 400

    host = find_host(host_name)
    if not host:
        return {"error": f"host '{host_name}' not found"}, 404

    release_enabled = parse_bool(payload.get("release", True), True)
    power_cfg = payload.get("powerAction")
    steps: List[Dict[str, Any]] = []
    success = True
    status_code = 200

    if lab_id:
        power_result = execute_power_phase(
            reservation_id,
            lab_id,
            host,
            "pre_end",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    if success and release_enabled:
        release_args = normalize_args(payload.get("releaseArgs"), ["--reboot"])
        ok, step = perform_command_step(
            host,
            reservation_id,
            lab_id,
            "release",
            "release-session",
            release_args,
        )
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and power_cfg:
        mode = power_cfg.get("mode", "shutdown")
        extra_args = normalize_args(power_cfg.get("args"), [])
        args = [mode] + extra_args
        ok, step = perform_command_step(
            host,
            reservation_id,
            lab_id,
            f"power:{mode}",
            "power",
            args,
        )
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and lab_id:
        power_result = execute_power_phase(
            reservation_id,
            lab_id,
            host,
            "post_end",
            payload,
        )
        steps.extend(power_result.get("steps", []))
        if not power_result.get("success"):
            success = False
            status_code = 502

    response = {
        "success": success,
        "reservationId": reservation_id,
        "host": host_name,
        "labId": lab_id,
        "steps": steps,
    }
    return response, status_code


__all__ = ["handle_reservation_end", "handle_reservation_start"]
