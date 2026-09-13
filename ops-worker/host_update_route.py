"""Composition for the dynamic host update HTTP route."""

import errno
from typing import Any, Callable, Dict, Optional, Tuple


def handle_host_update(
    host_name: str,
    payload: Any,
    *,
    update_host: Callable[[str, Dict[str, Any]], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    safe_host_inventory_entry: Callable[..., Dict[str, Any]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Update a dynamic host while preserving its public status and payload contract."""
    if not isinstance(payload, dict):
        return jsonify({"error": "host update payload must be an object"}), 400

    try:
        host_config, error = update_host(host_name, payload)
        if error:
            status = 409 if "static catalog" in error or "already exists" in error else 400
            return jsonify({"error": error}), status
        if host_config is None:
            return jsonify({"error": "host configuration could not be updated"}), 400
        count, reload_error = reload_hosts()
    except PermissionError:
        return jsonify({
            "error": "Ops host catalog is not writable; check the ops-data mount permissions",
            "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
        }), 503
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return jsonify({
                "error": "Ops host catalog is not writable; check the ops-data mount permissions",
                "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
            }), 503
        return internal_error_response("Failed to update ops host", exc)
    except Exception as exc:
        return internal_error_response("Failed to update ops host", exc)

    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500

    return jsonify({
        "updated": True,
        "hosts": count,
        "host": safe_host_inventory_entry(host_config, editable=True),
    })


__all__ = ["handle_host_update"]
