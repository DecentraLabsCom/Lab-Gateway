"""Internal Flask endpoints for provider-local power operations."""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Blueprint, current_app, jsonify, request

from power.models import ValidationError

from .drivers.base import PowerDriverError
from .service import PowerConfigError, PowerRuntime


power_bp = Blueprint("power", __name__)


def _runtime() -> Optional[PowerRuntime]:
    return current_app.extensions.get("power_runtime")


def _runtime_unavailable():
    return jsonify({"success": False, "error": "Power control is not configured"}), 503


def _payload() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def _public_operation(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Avoid returning device-specific exception details to the UI."""
    public = dict(operation)
    if not public.get("success"):
        public["message"] = "Power controller operation failed"
    return public


def _public_result(result: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(result)
    public["steps"] = [
        _public_operation(step) for step in result.get("steps", [])
    ]
    return public


@power_bp.get("/api/power/controllers")
def list_power_controllers():
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    return jsonify({"success": True, "controllers": runtime.describe_controllers()})


@power_bp.get("/api/power/policies")
def list_power_policies():
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    return jsonify({"success": True, "policies": runtime.describe_policies()})


@power_bp.put("/api/power/policies/<lab_id>")
def update_power_policy(lab_id: str):
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    body = _payload()
    provided_lab_id = str(body.get("labId", body.get("lab_id")) or "").strip()
    if provided_lab_id and provided_lab_id != str(lab_id):
        return jsonify({"success": False, "error": "labId does not match the URL"}), 400
    policy = dict(body)
    policy["labId"] = str(lab_id)
    policy.pop("lab_id", None)
    try:
        updated = runtime.update_policy(policy)
    except ValidationError:
        return jsonify({"success": False, "error": "Power policy is invalid"}), 400
    except PowerConfigError:
        return jsonify({"success": False, "error": "Power policy could not be persisted"}), 503
    return jsonify({"success": True, "policy": updated})


@power_bp.post("/api/power/mock/reset")
def reset_mock_power():
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    return jsonify({"success": True, "resetControllers": runtime.reset_mock()})


@power_bp.post("/api/power/controllers/<controller_id>/outlets/<outlet_id>/commands")
def manual_power_command(controller_id: str, outlet_id: str):
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    body = _payload()
    command = str(body.get("command") or "").strip().lower()
    action = command
    if command == "set_state":
        action = str(body.get("state") or "").strip().lower()
    if action not in {"on", "off", "cycle"}:
        return jsonify({"success": False, "error": "command must be set_state or cycle"}), 400
    try:
        result = runtime.executor.execute_manual(
            controller_id=controller_id,
            outlet_id=outlet_id,
            action=action,
            actor=str(body.get("actor") or "lab-manager").strip(),
            reason=str(body.get("reason") or "").strip() or None,
            idempotency_key=str(body.get("idempotencyKey") or body.get("idempotency_key") or "").strip(),
            off_seconds=int(body.get("offSeconds", body.get("off_seconds", 10))),
            allow_protected=_bool(body.get("allowProtected", body.get("allow_protected"))),
            maintenance=_bool(body.get("maintenance")),
        )
    except KeyError:
        return jsonify({"success": False, "error": "Power controller or outlet was not found"}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "Power operation is not permitted"}), 403
    except (TypeError, ValueError, ValidationError):
        return jsonify({"success": False, "error": "Power command is invalid"}), 400
    except PowerDriverError:
        return jsonify({"success": False, "error": "Power controller command failed"}), 502
    return jsonify({
        "success": result["success"],
        "operation": _public_operation(result),
    }), 200 if result["success"] else 502


def _execute_lab_phase(lab_id: str, phase: str):
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    body = _payload()
    reservation_id = str(body.get("reservationId") or body.get("reservation_id") or "").strip()
    if not reservation_id:
        return jsonify({"success": False, "error": "reservationId is required"}), 400
    actor = str(body.get("actor") or "lab-manager").strip()
    try:
        result = runtime.execute_policy(
            lab_id,
            reservation_id,
            phase,
            actor=actor,
            dry_run=_bool(body.get("dryRun", body.get("dry_run"))),
            local_mode=False,
        )
    except PermissionError:
        return jsonify({"success": False, "error": "Power operation is not permitted"}), 403
    except (ValidationError, KeyError):
        return jsonify({"success": False, "error": "Power phase request is invalid"}), 422
    status = 200 if result["success"] else 502
    return jsonify({
        "success": result["success"],
        "labId": lab_id,
        **_public_result(result),
    }), status


@power_bp.post("/api/labs/<lab_id>/power/start")
def start_lab_power(lab_id: str):
    return _execute_lab_phase(lab_id, "pre_start")


@power_bp.post("/api/labs/<lab_id>/power/end")
def end_lab_power(lab_id: str):
    return _execute_lab_phase(lab_id, "post_end")


@power_bp.get("/api/power/operations")
def list_power_operations():
    runtime = _runtime()
    if runtime is None:
        return _runtime_unavailable()
    reservation_id = request.args.get("reservationId") or request.args.get("reservation_id")
    return jsonify({
        "success": True,
        "operations": [
            _public_operation(operation)
            for operation in runtime.operations(reservation_id=reservation_id)
        ],
    })
