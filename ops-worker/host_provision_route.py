"""Composition for the dynamic host provisioning HTTP route."""

import errno
from typing import Any, Callable, Collection, Dict, Optional, Tuple


_CATALOG_NOT_WRITABLE_ERROR = {
    "error": "Ops host catalog is not writable; check the ops-data mount permissions",
    "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
}


def handle_host_provision(
    payload: Any,
    *,
    resolve_connection: Callable[[Any], Optional[Dict[str, Any]]],
    discover_candidate: Callable[[Dict[str, Any]], Dict[str, Any]],
    enough_discovery_signals: Collection[Any],
    build_host: Callable[[Dict[str, Any], Dict[str, Any]], Tuple[Optional[Dict[str, Any]], Optional[str]]],
    find_host: Callable[[str], Optional[Dict[str, Any]]],
    upsert_host: Callable[[Dict[str, Any]], None],
    reload_hosts: Callable[[], Tuple[int, Optional[str]]],
    safe_host_inventory_entry: Callable[..., Dict[str, Any]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[..., Any],
) -> Any:
    """Provision a host from a discovered Guacamole connection."""
    connection_id = payload.get("connectionId") or payload.get("connection_id")
    if connection_id in (None, ""):
        return jsonify({"error": "connectionId is required"}), 400

    connection = resolve_connection(connection_id)
    if not connection:
        return jsonify({"error": f"Guacamole connection {connection_id} not found"}), 404

    discovery = discover_candidate(connection)
    if discovery.get("status") not in enough_discovery_signals:
        return jsonify({
            "error": "insufficient discovery signal for ops host provisioning",
            "discovery": discovery,
        }), 409

    provision_payload = dict(payload)
    ops_host_draft = discovery.get("opsHostDraft")
    if isinstance(ops_host_draft, dict):
        discovered_path_fields = {
            "labstation_exe": "labstationExe",
            "local_mode_flag_path": "localModeFlagPath",
            "heartbeat_path": "heartbeatPath",
            "events_path": "eventsPath",
        }
        for source_key, payload_key in discovered_path_fields.items():
            if not str(provision_payload.get(payload_key) or "").strip():
                discovered_value = ops_host_draft.get(source_key)
                if discovered_value:
                    provision_payload[payload_key] = discovered_value
    if not str(provision_payload.get("mac") or "").strip():
        suggested_mac = ops_host_draft.get("mac") if isinstance(ops_host_draft, dict) else None
        if suggested_mac:
            provision_payload["mac"] = suggested_mac

    host_config, error = build_host(provision_payload, connection)
    if error:
        return jsonify({"error": error}), 400
    if host_config is None:
        return jsonify({"error": "host configuration could not be built"}), 400

    existing = find_host(host_config["name"])
    if existing:
        return jsonify({"error": f"host {host_config['name']} already exists"}), 409

    try:
        upsert_host(host_config)
        count, reload_error = reload_hosts()
    except PermissionError:
        return jsonify(_CATALOG_NOT_WRITABLE_ERROR), 503
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return jsonify(_CATALOG_NOT_WRITABLE_ERROR), 503
        return internal_error_response("Failed to provision ops host", exc)
    except Exception as exc:
        return internal_error_response("Failed to provision ops host", exc)

    if reload_error:
        return jsonify({"error": "Hosts configuration reload failed"}), 500

    return jsonify({
        "provisioned": True,
        "hosts": count,
        "host": safe_host_inventory_entry(host_config, editable=True),
        "discoveryStatus": discovery.get("status"),
    })


__all__ = ["handle_host_provision"]
