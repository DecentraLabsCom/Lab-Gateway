"""Composition for the per-lab AAS synchronization HTTP route."""

from typing import Any, Callable, Dict, Optional


def _safe_lab_id(lab_id: Any) -> str:
    return str(lab_id).replace("\r", "\\r").replace("\n", "\\n")


def handle_aas_lab_sync(
    lab_id: str,
    payload: Any,
    *,
    find_host_by_lab: Callable[[str], Optional[Dict[str, Any]]],
    parse_bool: Callable[[Any, bool], bool],
    poll_heartbeat: Callable[..., Dict[str, Any]],
    load_persisted_heartbeat: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]],
    sync_lab: Callable[[str, Dict[str, Any], Optional[Dict[str, Any]]], Dict[str, Any]],
    log_warning: Callable[..., Any],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Synchronize one lab while preserving heartbeat and result contracts."""
    host = find_host_by_lab(lab_id)
    if not host:
        return jsonify({"error": f"No host mapping found for labId '{lab_id}'"}), 404

    include_heartbeat = parse_bool(payload.get("includeHeartbeat", False), False)
    heartbeat_data: Optional[Dict[str, Any]] = None
    if include_heartbeat:
        try:
            poll_result = poll_heartbeat(host, include_events=False)
            heartbeat_data = poll_result.get("heartbeat")
        except Exception as exc:
            log_warning(
                "AAS sync: could not poll heartbeat for lab %s: %s",
                _safe_lab_id(lab_id),
                type(exc).__name__,
            )
    elif load_persisted_heartbeat is not None:
        try:
            heartbeat_data = load_persisted_heartbeat(lab_id, host)
        except Exception as exc:
            log_warning(
                "AAS sync: could not load heartbeat from DB for lab %s: %s",
                _safe_lab_id(lab_id),
                type(exc).__name__,
            )

    result = sync_lab(str(lab_id), host, heartbeat_data)

    if result.get("disabled"):
        return jsonify(result), 200

    if result.get("error"):
        return jsonify({"detail": result["error"], **result}), 502

    return jsonify(result), 200


__all__ = ["handle_aas_lab_sync"]
