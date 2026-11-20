"""Reservation lifecycle operations with explicit runtime dependencies."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional, Tuple

from station_action_policy import StationActionPolicyError


def handle_reservation_start(
    payload: Dict[str, Any],
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    resolve_host_by_lab: Callable[[str], Optional[Mapping[str, Any]]],
    get_mandatory_field: Callable[..., Optional[str]],
    parse_bool: Callable[[Any, bool], bool],
    execute_power_phase: Callable[[str, Optional[str], Mapping[str, Any], str, Dict[str, Any]], Dict[str, Any]],
    perform_wake_step: Callable[[Mapping[str, Any], str, Optional[str], Dict[str, Any]], Tuple[bool, Dict[str, Any]]],
    perform_command_step: Callable[..., Tuple[bool, Dict[str, Any]]],
    normalize_args: Callable[[Any, Optional[List[str]]], List[str]],
    resolve_station_lease_context: Optional[Callable[..., Dict[str, Any]]] = None,
    authorize_remote_session_handoff: Optional[Callable[..., List[str]]] = None,
    authoritative_reservation: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    reservation_id = get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = get_mandatory_field(payload, "host", "hostName")
    lab_id = get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or (not host_name and not lab_id):
        return {"error": "reservationId and either host or labId are required"}, 400

    if lab_id:
        host = resolve_host_by_lab(lab_id)
    else:
        host = find_host(host_name or "")
    if not host:
        if lab_id:
            return {"error": f"no registered host found for lab '{lab_id}'"}, 404
        return {"error": f"host '{host_name}' not found"}, 404
    host_name = str(host.get("name") or host_name or "")

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

    if success and prepare_enabled:
        prepare_args = normalize_args(
            payload.get("prepareArgs"),
            [f"--guard-grace={guard_grace}"],
        )
        if any(str(arg).split("=", 1)[0] == "--unreserved-remote-labuser-sessions" for arg in prepare_args):
            return {"error": "remote-session handoff authorization is Gateway-managed"}, 400
        if authorize_remote_session_handoff is not None:
            try:
                authorized_args = authorize_remote_session_handoff(
                    host,
                    None,
                    str(reservation_id),
                    authoritative_reservation=authoritative_reservation,
                )
                if not isinstance(authorized_args, list) or any(not isinstance(arg, str) for arg in authorized_args):
                    raise StationActionPolicyError(
                        "STATION_RESERVATION_STATE_UNKNOWN",
                        "Remote-session handoff authorization is invalid",
                    )
                prepare_args.extend(authorized_args)
            except StationActionPolicyError as exc:
                steps.append({
                    "action": "prepare",
                    "success": False,
                    "status": "failed",
                    "message": str(exc),
                    "details": {"code": exc.code},
                })
                success = False
                status_code = 409
            except Exception:
                steps.append({
                    "action": "prepare",
                    "success": False,
                    "status": "failed",
                    "message": "Remote-session reservation state could not be verified",
                    "details": {"code": "STATION_RESERVATION_STATE_UNKNOWN"},
                })
                success = False
                status_code = 409
        management_value = host.get("management")
        management = management_value if isinstance(management_value, Mapping) else {}
        dispatcher_request = None
        dispatcher_request_error = None
        if success and str(management.get("transport") or host.get("management_transport") or "winrm").lower() in {"ssh", "winrm"}:
            try:
                if resolve_station_lease_context is None:
                    raise ValueError("resolver unavailable")
                lease_context_kwargs: Dict[str, Any] = {}
                if authoritative_reservation is not None:
                    lease_context_kwargs["authoritative_reservation"] = authoritative_reservation
                prepare_attempt = str(payload.get("prepareAttempt") or "").strip()
                if prepare_attempt:
                    lease_context_kwargs["prepare_attempt"] = prepare_attempt
                prepare_issued_at = payload.get("prepareIssuedAt")
                if prepare_issued_at is not None:
                    lease_context_kwargs["prepare_issued_at"] = prepare_issued_at
                dispatcher_request = resolve_station_lease_context(
                    reservation_id,
                    lab_id,
                    host,
                    "prepare-session",
                    **lease_context_kwargs,
                )
            except Exception:
                dispatcher_request_error = "authoritative reservation lease context is unavailable"
        step_args = (host, reservation_id, lab_id, "prepare", "prepare-session", prepare_args)
        if success:
            if dispatcher_request is not None or dispatcher_request_error:
                ok, step = perform_command_step(
                    *step_args,
                    dispatcher_request=dispatcher_request,
                    dispatcher_request_error=dispatcher_request_error,
                )
            else:
                ok, step = perform_command_step(*step_args)
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
    resolve_host_by_lab: Callable[[str], Optional[Mapping[str, Any]]],
    get_mandatory_field: Callable[..., Optional[str]],
    parse_bool: Callable[[Any, bool], bool],
    execute_power_phase: Callable[[str, Optional[str], Mapping[str, Any], str, Dict[str, Any]], Dict[str, Any]],
    perform_command_step: Callable[..., Tuple[bool, Dict[str, Any]]],
    normalize_args: Callable[[Any, Optional[List[str]]], List[str]],
    resolve_station_lease_context: Optional[Callable[..., Dict[str, Any]]] = None,
    authoritative_reservation: Optional[Mapping[str, Any]] = None,
    reconciliation_attempt: Optional[str] = None,
    reconciliation_only: bool = False,
    shutdown_ops_optional: bool = False,
) -> Tuple[Dict[str, Any], int]:
    reservation_id = get_mandatory_field(payload, "reservationId", "reservation_id")
    host_name = get_mandatory_field(payload, "host", "hostName")
    lab_id = get_mandatory_field(payload, "labId", "lab_id")

    if not reservation_id or (not host_name and not lab_id):
        return {"error": "reservationId and either host or labId are required"}, 400

    if lab_id:
        host = resolve_host_by_lab(lab_id)
    else:
        host = find_host(host_name or "")
    if not host:
        if lab_id:
            return {"error": f"no registered host found for lab '{lab_id}'"}, 404
        return {"error": f"host '{host_name}' not found"}, 404
    host_name = str(host.get("name") or host_name or "")

    release_enabled = parse_bool(payload.get("release", True), True)
    power_cfg = payload.get("powerAction")
    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    success = True
    status_code = 200

    if lab_id and not reconciliation_only:
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
        release_args = normalize_args(payload.get("releaseArgs"), [])
        if reconciliation_only and "--protect-local-sessions" not in release_args:
            release_args.append("--protect-local-sessions")
        management_value = host.get("management")
        management = management_value if isinstance(management_value, Mapping) else {}
        dispatcher_request = None
        dispatcher_request_error = None
        if str(management.get("transport") or host.get("management_transport") or "winrm").lower() in {"ssh", "winrm"}:
            try:
                if resolve_station_lease_context is None:
                    raise ValueError("resolver unavailable")
                lease_context_kwargs: Dict[str, Any] = {}
                if authoritative_reservation is not None:
                    lease_context_kwargs["authoritative_reservation"] = authoritative_reservation
                if reconciliation_attempt is not None:
                    lease_context_kwargs["reconciliation_attempt"] = reconciliation_attempt
                release_attempt = str(payload.get("releaseAttempt") or "").strip()
                if release_attempt:
                    lease_context_kwargs["release_attempt"] = release_attempt
                release_issued_at = payload.get("releaseIssuedAt")
                if release_issued_at is not None:
                    lease_context_kwargs["release_issued_at"] = release_issued_at
                dispatcher_request = resolve_station_lease_context(
                    reservation_id,
                    lab_id,
                    host,
                    "release-session",
                    **lease_context_kwargs,
                )
            except Exception:
                dispatcher_request_error = "authoritative reservation lease context is unavailable"
        step_args = (host, reservation_id, lab_id, "release", "release-session", release_args)
        if dispatcher_request is not None or dispatcher_request_error:
            ok, step = perform_command_step(
                *step_args,
                dispatcher_request=dispatcher_request,
                dispatcher_request_error=dispatcher_request_error,
            )
        else:
            ok, step = perform_command_step(*step_args)
        steps.append(step)
        if not ok:
            success = False
            status_code = 502

    if success and power_cfg and not reconciliation_only:
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
            if shutdown_ops_optional:
                warnings.append("Configured station shutdown did not complete; reservation cleanup continued")
            else:
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
    if warnings:
        response["warnings"] = warnings
    return response, status_code


__all__ = ["handle_reservation_end", "handle_reservation_start"]
