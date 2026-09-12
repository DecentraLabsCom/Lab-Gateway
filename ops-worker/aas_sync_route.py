"""Composition for the Lab Manager AAS synchronization route."""

from typing import Any, Callable, Dict, Mapping, Optional


def handle_aas_sync(
    payload: Mapping[str, Any],
    *,
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    sync_lab: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    log_failure: Callable[..., Any],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Sync all labs mapped to a host while preserving per-lab error isolation."""
    host_name = payload.get("host")
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found in config"}), 404

    labs = host.get("labs", [])
    if not labs:
        return jsonify({
            "host": host_name,
            "labs": [],
            "message": "No labs mapped to this host",
        }), 200

    results = []
    for lab_id in labs:
        try:
            result = sync_lab(str(lab_id), host)
            results.append({"labId": str(lab_id), **result})
        except Exception as exc:
            log_failure("AAS sync failed for lab %s", lab_id)
            results.append({"labId": str(lab_id), "error": "AAS synchronization failed"})
    return jsonify({"host": host_name, "labs": results}), 200


__all__ = ["handle_aas_sync"]
