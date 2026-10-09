"""HTTP boundary for Wake Ops configuration and manual wake requests."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from wake_ops_service import WAKE_EVIDENCE_MAX_AGE_SECONDS, WakeOpsValidationError


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _schedule_response(schedule: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        **schedule,
        "lastScheduledAt": _iso(schedule.get("lastScheduledAt")),
        "lastStartedAt": _iso(schedule.get("lastStartedAt")),
        "lastFinishedAt": _iso(schedule.get("lastFinishedAt")),
    }


def _evidence_response(operation: Optional[Mapping[str, Any]], now: datetime) -> Dict[str, Any]:
    if not operation:
        return {"state": "unknown", "validForSeconds": WAKE_EVIDENCE_MAX_AGE_SECONDS}
    created_at = operation.get("createdAt")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if not operation.get("success"):
        return {
            "state": "failed",
            "createdAt": _iso(created_at),
            "ageSeconds": None if not created_at else max(0, int((now - created_at).total_seconds())),
            "validForSeconds": WAKE_EVIDENCE_MAX_AGE_SECONDS,
            "message": operation.get("message"),
        }
    age = None if not created_at else max(0, int((now - created_at).total_seconds()))
    verified = bool(operation.get("success")) and age is not None and age <= WAKE_EVIDENCE_MAX_AGE_SECONDS
    return {
        "state": "verified" if verified else "expired",
        "createdAt": _iso(created_at),
        "ageSeconds": age,
        "validForSeconds": WAKE_EVIDENCE_MAX_AGE_SECONDS,
        "message": operation.get("message"),
    }


def create_wake_ops_blueprint(
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    get_schedule: Callable[[str], Mapping[str, Any]],
    save_schedule: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    get_latest_wake: Callable[[str], Optional[Mapping[str, Any]]],
    manual_wake: Callable[[str], Mapping[str, Any]],
    now: Callable[[], datetime],
    internal_error_response: Callable[[str], Any],
) -> Blueprint:
    blueprint = Blueprint("wake_ops", __name__)

    def require_host(host_name: str) -> Optional[Any]:
        if find_host(host_name):
            return None
        return jsonify({"error": "Unknown host"}), 404

    @blueprint.get("/api/wake-ops/<host_name>")
    def api_wake_ops(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        try:
            current = now()
            response = jsonify(
                {
                    "host": host_name,
                    "schedule": _schedule_response(get_schedule(host_name)),
                    "evidence": _evidence_response(get_latest_wake(host_name), current),
                }
            )
        except Exception:  # pylint: disable=broad-except
            response = None
        if response is None:
            # The exception is discarded; this callback receives a fixed context outside the handler.
            # codeql[py/stack-trace-exposure]
            return internal_error_response("Unable to load Wake Ops")
        return response

    @blueprint.put("/api/wake-ops/<host_name>")
    def api_wake_ops_update(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        try:
            payload = request.get_json(force=True, silent=True) or {}
            saved = save_schedule(host_name, payload)
            response = jsonify({"host": host_name, "schedule": _schedule_response(saved)})
        except WakeOpsValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:  # pylint: disable=broad-except
            response = None
        if response is None:
            # The exception is discarded; this callback receives a fixed context outside the handler.
            # codeql[py/stack-trace-exposure]
            return internal_error_response("Unable to save Wake Ops")
        return response

    @blueprint.post("/api/wake-ops/<host_name>/wake")
    def api_wake_ops_manual_wake(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        try:
            result = manual_wake(host_name)
            response = jsonify(result), 200 if result.get("success") else 502
        except Exception:  # pylint: disable=broad-except
            response = None
        if response is None:
            # The exception is discarded; this callback receives a fixed context outside the handler.
            # codeql[py/stack-trace-exposure]
            return internal_error_response("Unable to execute manual Wake Ops wake")
        return response

    return blueprint


__all__ = ["create_wake_ops_blueprint"]
