"""HTTP boundary for per-station Shutdown Ops configuration and manual actions."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from wake_ops_service import WakeOpsValidationError


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


def create_shutdown_ops_blueprint(
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    get_schedule: Callable[[str], Mapping[str, Any]],
    save_schedule: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    manual_shutdown: Callable[[str], Mapping[str, Any]],
) -> Blueprint:
    blueprint = Blueprint("shutdown_ops", __name__)

    def require_host(host_name: str) -> Optional[Any]:
        if find_host(host_name):
            return None
        return jsonify({"error": "Unknown host"}), 404

    @blueprint.get("/api/shutdown-ops/<host_name>")
    def api_shutdown_ops(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        return jsonify(
            {"host": host_name, "schedule": _schedule_response(get_schedule(host_name))}
        )

    @blueprint.put("/api/shutdown-ops/<host_name>")
    def api_shutdown_ops_update(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        try:
            payload = request.get_json(force=True, silent=True) or {}
            if not isinstance(payload, Mapping):
                return jsonify({"error": "Invalid Shutdown Ops schedule"}), 400
            saved = save_schedule(host_name, payload)
        except WakeOpsValidationError:
            return jsonify({"error": "Invalid Shutdown Ops schedule"}), 400
        return jsonify({"host": host_name, "schedule": _schedule_response(saved)})

    @blueprint.post("/api/shutdown-ops/<host_name>/shutdown")
    def api_shutdown_ops_manual_shutdown(host_name: str):
        missing = require_host(host_name)
        if missing:
            return missing
        result = manual_shutdown(host_name)
        if result.get("success"):
            status_code = 200
        elif result.get("status") == "blocked":
            status_code = 409
        else:
            status_code = 502
        return jsonify(result), status_code

    return blueprint


__all__ = ["create_shutdown_ops_blueprint"]
