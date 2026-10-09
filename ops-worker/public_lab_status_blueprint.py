"""Flask boundary for the intentionally small public lab-status projection."""

from collections.abc import Callable
from typing import Any

from flask import Blueprint, jsonify, request

from public_lab_status_route import build_public_lab_status_response, parse_lab_ids


def create_public_lab_status_blueprint(
    *,
    get_db_engine: Callable[[], Any],
    resolve_lab_associations: Callable[[], Any],
    resolve_lab_status_targets: Callable[[], Any],
    fetch_latest_heartbeat: Callable[[Any, str], Any],
    probe_lab_targets: Callable[[Any], Any],
    now: Callable[[], Any],
    max_age_seconds: Callable[[], int],
    resolve_lab_resources: Callable[[], Any] = lambda: [],
    fetch_fmu_runner_status: Callable[[str], Any] = lambda _lab_id: None,
    fetch_latest_wake_operations: Callable[[Any, Any], Any] = lambda _connection, _lab_ids: {},
) -> Blueprint:
    blueprint = Blueprint("public_lab_status", __name__)

    @blueprint.get("/public/labs/status")
    def public_lab_status():
        try:
            values = request.args.getlist("labId") + request.args.getlist("labIds")
            lab_ids = parse_lab_ids(values)
        except ValueError:
            return jsonify({"error": "Invalid lab IDs", "code": "INVALID_LAB_IDS"}), 400

        try:
            payload = build_public_lab_status_response(
                lab_ids,
                engine=get_db_engine(),
                resolve_lab_associations=resolve_lab_associations,
                resolve_lab_status_targets=resolve_lab_status_targets,
                resolve_lab_resources=resolve_lab_resources,
                fetch_latest_heartbeat=fetch_latest_heartbeat,
                probe_lab_targets=probe_lab_targets,
                fetch_fmu_runner_status=fetch_fmu_runner_status,
                fetch_latest_wake_operations=fetch_latest_wake_operations,
                now=now,
                max_age_seconds=max_age_seconds(),
            )
        except Exception:  # pylint: disable=broad-except
            payload = None
        if payload is None:
            # Public consumers should degrade to an unknown LED, without host
            # or database details in the response.
            return jsonify({
                "error": "Lab status is temporarily unavailable",
                "code": "LAB_STATUS_UNAVAILABLE",
            }), 503
        return jsonify(payload), 200

    return blueprint


__all__ = ["create_public_lab_status_blueprint"]
