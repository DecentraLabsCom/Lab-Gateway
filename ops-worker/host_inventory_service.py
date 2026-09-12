"""Public host inventory composition with explicit source dependencies."""

from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Optional


def build_host_inventory(
    hosts: Sequence[Dict[str, Any]],
    dynamic_config: Dict[str, Any],
    guacamole_connections: Sequence[Dict[str, Any]],
    guacamole_error: Optional[str],
    *,
    normalize_key: Callable[[Any], str],
    safe_entry: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the public inventory while matching hosts to Guacamole entries."""
    dynamic_host_names = {
        normalize_key(host.get("name"))
        for host in dynamic_config.get("hosts", [])
        if isinstance(host, dict) and normalize_key(host.get("name"))
    }
    claimed_ids = set()
    host_entries: List[Dict[str, Any]] = []

    for host in hosts:
        match_keys = {
            normalize_key(host.get("name")),
            normalize_key(host.get("address")),
        }
        match_keys.discard("")
        matches = [
            connection
            for connection in guacamole_connections
            if normalize_key(connection.get("hostname")) in match_keys
        ]
        for connection in matches:
            claimed_ids.add(connection.get("id"))

        if len(matches) == 1:
            status = "single"
        elif len(matches) > 1:
            status = "multiple"
        else:
            status = "none"

        entry = safe_entry(
            host,
            editable=normalize_key(host.get("name")) in dynamic_host_names,
        )
        entry["guacamole"] = {
            "status": status,
            "connections": matches,
        }
        host_entries.append(entry)

    unmatched = [
        connection
        for connection in guacamole_connections
        if connection.get("id") not in claimed_ids
    ]

    return {
        "hosts": host_entries,
        "guacamoleAvailable": guacamole_error is None,
        "guacamoleError": guacamole_error,
        "guacamoleUnmatched": unmatched,
    }
