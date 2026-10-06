"""Management API for SSH credential enrollment and neutral station commands."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional
from uuid import uuid4

from flask import Blueprint, jsonify, request

from station_errors import StationError


def create_station_api_blueprint(
    *,
    find_host: Callable[[str], Optional[Mapping[str, Any]]],
    run_station_command: Callable[..., Dict[str, Any]],
    generate_ssh_credential: Callable[..., Dict[str, str]],
    public_ssh_credential: Callable[[str], Optional[Dict[str, str]]],
    delete_ssh_credential: Callable[[str], bool],
    probe_ssh_host_key: Callable[[Mapping[str, Any]], Dict[str, str]],
    confirm_ssh_host_key: Callable[[Mapping[str, Any], str], Dict[str, Any]],
    ssh_trust_status: Callable[[Mapping[str, Any]], Dict[str, Any]],
    delete_ssh_trust: Callable[[Mapping[str, Any]], bool],
    probe_station: Callable[[Mapping[str, Any]], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("station_api", __name__)

    def error_response(exc: StationError):
        request_id = str(uuid4())
        status = 409 if "TRUST" in exc.code else 401 if exc.code == "STATION_AUTH_FAILED" else 502
        return jsonify({"error": exc.message, "code": exc.code, "transport": exc.transport, "requestId": request_id}), status

    @bp.post("/api/station/command")
    def command():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON request body is required"}), 400
        host_name = str(payload.get("host") or "").strip()
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        station_command = str(payload.get("command") or "")
        args = payload.get("args", [])
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            return jsonify({"error": "args must be a string array"}), 400
        try:
            result = run_station_command(host, station_command, args, request_id=str(uuid4()))
            return jsonify(result), 200 if int(result.get("exitCode", 2)) < 2 else 409
        except StationError as exc:
            return error_response(exc)
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "STATION_COMMAND_REJECTED"}), 400
        except Exception:
            return jsonify({"error": "Station command failed", "code": "STATION_COMMAND_FAILED"}), 502

    @bp.post("/api/station/credentials/<credential_ref>")
    def create_credential(credential_ref: str):
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON request body must be an object"}), 400
        try:
            result = generate_ssh_credential(credential_ref, username=payload.get("username", "labstation-ops"))
            return jsonify(result), 201
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc), "code": "STATION_CREDENTIAL_INVALID"}), 400

    @bp.get("/api/station/credentials/<credential_ref>")
    def get_credential(credential_ref: str):
        try:
            credential = public_ssh_credential(credential_ref)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not credential:
            return jsonify({"error": "SSH credential was not found", "code": "STATION_CREDENTIAL_MISSING"}), 404
        return jsonify(credential)

    @bp.delete("/api/station/credentials/<credential_ref>")
    def remove_credential(credential_ref: str):
        try:
            return jsonify({"deleted": bool(delete_ssh_credential(credential_ref))})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @bp.post("/api/station/hosts/<host_name>/trust/preview")
    def preview_trust(host_name: str):
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        try:
            return jsonify(probe_ssh_host_key(host))
        except StationError as exc:
            return error_response(exc)

    @bp.post("/api/station/hosts/<host_name>/trust/confirm")
    def confirm_trust(host_name: str):
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON request body must be an object"}), 400
        fingerprint = payload.get("fingerprint", "")
        if not isinstance(fingerprint, str):
            return jsonify({"error": "fingerprint must be a string", "code": "STATION_TRUST_INVALID"}), 400
        fingerprint = fingerprint.strip()
        try:
            return jsonify(confirm_ssh_host_key(host, fingerprint)), 201
        except StationError as exc:
            return error_response(exc)
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "STATION_TRUST_INVALID"}), 400

    @bp.get("/api/station/hosts/<host_name>/trust")
    def get_trust(host_name: str):
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        return jsonify(ssh_trust_status(host))

    @bp.delete("/api/station/hosts/<host_name>/trust")
    def remove_trust(host_name: str):
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        return jsonify({"deleted": bool(delete_ssh_trust(host))})

    @bp.post("/api/station/hosts/<host_name>/verify")
    def verify(host_name: str):
        host = find_host(host_name)
        if not host:
            return jsonify({"error": "Station was not found", "code": "STATION_NOT_FOUND"}), 404
        try:
            return jsonify(probe_station(host))
        except StationError as exc:
            return error_response(exc)

    return bp


__all__ = ["create_station_api_blueprint"]
