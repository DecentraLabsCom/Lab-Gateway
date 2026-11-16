"""Profile-aware policy for operator-triggered physical Station actions."""

import json
from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional


_MANUAL_PREPARE_REMOTE_SESSION_MESSAGE = (
    "Manual Prepare deletes LABUSER temporary files, Downloads, and lab scratch data and may interrupt open apps. "
    "An active remote LABUSER session was detected, so no cleanup ran. Wait for it to disconnect before retrying."
)


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
    authorize_remote_session_handoff: Optional[Callable[..., List[str]]] = None,
) -> List[str]:
    """Fail closed when a physical action is invalid for the Station profile."""
    command = str(command or "").strip().lower()
    local_mode_action = args[0].strip().lower() if args else ""
    if command == "prepare-session" and any(
        str(arg).split("=", 1)[0] == "--unreserved-remote-labuser-sessions"
        for arg in args
    ):
        raise StationActionPolicyError(
            "STATION_COMMAND_REJECTED",
            "Remote-session handoff authorization is Gateway-managed",
        )
    if command not in {"prepare-session", "release-session"} and not (
        command == "local-mode" and local_mode_action == "set"
    ):
        return list(args)

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
        remote_ids = sessions.get("remoteLabUserSessionIds")
        if remote_ids is not None and (
            not isinstance(remote_ids, list)
            or any(not isinstance(value, str) or not value.strip() for value in remote_ids)
        ):
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session inventory is invalid; local mode was not enabled",
            )
        ids_active = isinstance(remote_ids, list) and bool(remote_ids)
        if remote_session is not False or ids_active:
            code = (
                "STATION_REMOTE_SESSION_ACTIVE"
                if remote_session is True or ids_active
                else "STATION_SESSION_STATE_UNKNOWN"
            )
            message = (
                "An active remote lab-user session prevents enabling local mode"
                if remote_session is True or ids_active
                else "Remote lab-user session state is unknown; local mode was not enabled"
            )
            raise StationActionPolicyError(code, message)
    if command in {"prepare-session", "release-session"}:
        sessions_value = status.get("sessions")
        sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
        if sessions.get("queryOk") is not True:
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Station session inventory is unavailable; the operation was not sent",
            )
        remote_labuser_session = sessions.get("labUserRemoteActive", status.get("labUserRemoteActive"))
        remote_session_ids = sessions.get("remoteLabUserSessionIds")
        if not isinstance(remote_labuser_session, bool):
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session state is unavailable; the operation was not sent",
            )
        if remote_session_ids is not None and (
            not isinstance(remote_session_ids, list)
            or any(not isinstance(value, str) or not value.strip() for value in remote_session_ids)
        ):
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session inventory is invalid; the operation was not sent",
            )
        has_remote_session = remote_labuser_session is True or (
            isinstance(remote_session_ids, list) and bool(remote_session_ids)
        )
        if command == "release-session" and (has_remote_session or remote_labuser_session is not False):
            code = (
                "STATION_REMOTE_SESSION_ACTIVE"
                if remote_labuser_session is True or (isinstance(remote_session_ids, list) and remote_session_ids)
                else "STATION_SESSION_STATE_UNKNOWN"
            )
            message = (
                "An active remote LABUSER session is using the Station; the operation was not sent"
                if has_remote_session
                else "Remote LABUSER session state is unknown; the operation was not sent"
            )
            raise StationActionPolicyError(code, message)

    if command == "prepare-session":
        local_mode = status.get("localModeEnabled")
        if profile == "hybrid" and local_mode is not False:
            code = "STATION_LOCAL_MODE_ACTIVE" if local_mode is True else "STATION_LOCAL_MODE_UNKNOWN"
            message = (
                "Local mode is active; prepare was not sent"
                if local_mode is True
                else "Local mode state is unknown; prepare was not sent"
            )
            raise StationActionPolicyError(code, message)
        sessions_value = status.get("sessions")
        sessions = sessions_value if isinstance(sessions_value, Mapping) else {}
        remote_labuser_session = sessions.get("labUserRemoteActive", status.get("labUserRemoteActive"))
        remote_session_ids = sessions.get("remoteLabUserSessionIds")
        if remote_session_ids is not None and (
            not isinstance(remote_session_ids, list)
            or any(not isinstance(value, str) or not value.strip() for value in remote_session_ids)
        ):
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session inventory is invalid; prepare was not sent",
            )
        if not isinstance(remote_labuser_session, bool):
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session state is unavailable; prepare was not sent",
            )
        has_remote_session = remote_labuser_session is True or bool(remote_session_ids)
        if remote_labuser_session is True and not remote_session_ids:
            raise StationActionPolicyError(
                "STATION_SESSION_STATE_UNKNOWN",
                "Remote LABUSER session identity is unavailable; prepare was not sent",
            )
        if has_remote_session:
            if not remote_session_ids:
                raise StationActionPolicyError(
                    "STATION_SESSION_STATE_UNKNOWN",
                    "Remote LABUSER session identity is unavailable; prepare was not sent",
                )
            if authorize_remote_session_handoff is None:
                raise StationActionPolicyError(
                    "STATION_RESERVATION_STATE_UNKNOWN",
                    _MANUAL_PREPARE_REMOTE_SESSION_MESSAGE,
                )
            authorized_args = authorize_remote_session_handoff(host, status, None)
            if not isinstance(authorized_args, list) or not authorized_args:
                raise StationActionPolicyError(
                    "STATION_RESERVATION_STATE_UNKNOWN",
                    _MANUAL_PREPARE_REMOTE_SESSION_MESSAGE,
                )
            return list(args) + authorized_args

    return list(args)


__all__ = ["StationActionPolicyError", "validate_operator_station_action"]
