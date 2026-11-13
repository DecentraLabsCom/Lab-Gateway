"""Profile-aware policy for operator-triggered physical Station actions."""

import json
from collections.abc import Callable, Mapping
from typing import Any, Dict, List


class StationActionPolicyError(ValueError):
    """A Station action conflicts with its reported profile or state."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _station_status(
    host: Mapping[str, Any],
    run_station_command: Callable[..., Dict[str, Any]],
) -> Mapping[str, Any]:
    result = run_station_command(host, "status-json", [])
    try:
        exit_code = int(result.get("exitCode", result.get("exit_code", 2)))
    except (TypeError, ValueError):
        exit_code = 2
    if exit_code >= 2:
        raise StationActionPolicyError(
            "STATION_STATUS_UNAVAILABLE",
            "Station status is unavailable; the operation was not sent",
        )
    try:
        payload = json.loads(str(result.get("stdout") or "").lstrip("\ufeff"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise StationActionPolicyError(
            "STATION_STATUS_INVALID",
            "Station status is invalid; the operation was not sent",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StationActionPolicyError(
            "STATION_STATUS_INVALID",
            "Station status is invalid; the operation was not sent",
        )
    status = payload.get("status")
    return status if isinstance(status, Mapping) else payload


def _profile(status: Mapping[str, Any]) -> str:
    profile = str(status.get("profile") or status.get("stationProfile") or "").strip().lower()
    if profile == "server":
        return "dedicated"
    return profile


def validate_operator_station_action(
    host: Mapping[str, Any],
    command: str,
    args: List[str],
    *,
    run_station_command: Callable[..., Dict[str, Any]],
) -> None:
    """Fail closed when a physical action is invalid for the Station profile."""
    command = str(command or "").strip().lower()
    local_mode_action = args[0].strip().lower() if args else ""
    if command not in {"prepare-session", "release-session"} and not (
        command == "local-mode" and local_mode_action == "set"
    ):
        return

    status = _station_status(host, run_station_command)
    profile = _profile(status)
    if profile not in {"dedicated", "hybrid", "fmu-only"}:
        raise StationActionPolicyError(
            "STATION_PROFILE_UNKNOWN",
            "Station profile is unknown; refresh status before running this operation",
        )

    if command in {"prepare-session", "release-session"} and profile == "fmu-only":
        raise StationActionPolicyError(
            "STATION_PROFILE_UNSUPPORTED",
            "Physical session operations are not supported by the fmu-only profile",
        )
    if command == "local-mode" and profile != "hybrid":
        raise StationActionPolicyError(
            "STATION_PROFILE_UNSUPPORTED",
            "Local mode can only be enabled on a hybrid Station",
        )
    if command == "local-mode":
        sessions_value = status.get("sessions")
        sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
        if sessions.get("queryOk") is not True:
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Station session inventory is unavailable; local mode was not enabled",
            )
        remote_session = sessions.get("labUserRemoteActive", status.get("labUserRemoteActive"))
        if remote_session is not False:
            code = "STATION_REMOTE_SESSION_ACTIVE" if remote_session is True else "STATION_SESSION_STATE_UNKNOWN"
            message = (
                "An active remote lab-user session prevents enabling local mode"
                if remote_session is True
                else "Remote lab-user session state is unknown; local mode was not enabled"
            )
            raise StationActionPolicyError(code, message)
    if command == "prepare-session":
        local_mode = status.get("localModeEnabled")
        if local_mode is not False:
            code = "STATION_LOCAL_MODE_ACTIVE" if local_mode is True else "STATION_LOCAL_MODE_UNKNOWN"
            message = (
                "Local mode is active; prepare was not sent"
                if local_mode is True
                else "Local mode state is unknown; prepare was not sent"
            )
            raise StationActionPolicyError(code, message)
        sessions_value = status.get("sessions")
        sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
        if sessions.get("queryOk") is not True:
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Station session inventory is unavailable; prepare was not sent",
            )
        if profile == "dedicated":
            local_session = status.get("localSessionActive", sessions.get("localSessionActive"))
            if local_session is not False:
                code = "STATION_LOCAL_SESSION_ACTIVE" if local_session is True else "STATION_SESSION_STATE_UNKNOWN"
                message = (
                    "An unexpected interactive session is active on the dedicated Station"
                    if local_session is True
                    else "Station session state is unknown; prepare was not sent"
                )
                raise StationActionPolicyError(code, message)


__all__ = ["StationActionPolicyError", "validate_operator_station_action"]
