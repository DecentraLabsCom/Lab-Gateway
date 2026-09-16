"""Public host inventory composition with explicit source dependencies."""

from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Optional


def connection_matches_host(
    host: Dict[str, Any],
    connection: Optional[Dict[str, Any]],
    *,
    normalize_key: Callable[[Any], str],
) -> bool:
    """Return whether a Guacamole connection belongs to a registered host."""
    if not isinstance(connection, dict):
        return False

    hostname_key = normalize_key(connection.get("hostname"))
    if not hostname_key:
        return False

    match_keys = {
        normalize_key(host.get("name")),
        normalize_key(host.get("address")),
    }
    match_keys.discard("")
    return hostname_key in match_keys


def find_unique_host_for_connection(
    hosts: Sequence[Dict[str, Any]],
    connection: Optional[Dict[str, Any]],
    *,
    normalize_key: Callable[[Any], str],
) -> Optional[Dict[str, Any]]:
    """Return the only registered host matching a Guacamole connection."""
    matches = [
        host
        for host in hosts
        if connection_matches_host(host, connection, normalize_key=normalize_key)
    ]
    return matches[0] if len(matches) == 1 else None


def build_host_inventory_from_sources(
    registry: Any,
    *,
    hosts_lock: Any,
    load_dynamic_config: Callable[[], Dict[str, Any]],
    load_guacamole_connections: Callable[[], tuple[Sequence[Dict[str, Any]], Optional[str]]],
    normalize_key: Callable[[Any], str],
    safe_entry: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Collect live inventory sources under the catalog lock and project them."""
    with hosts_lock:
        hosts = registry.all_hosts()
    dynamic_config = load_dynamic_config()
    guacamole_connections, guacamole_error = load_guacamole_connections()
    return build_host_inventory(
        hosts,
        dynamic_config,
        guacamole_connections,
        guacamole_error,
        normalize_key=normalize_key,
        safe_entry=safe_entry,
    )


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
        matches = [
            connection
            for connection in guacamole_connections
            if connection_matches_host(host, connection, normalize_key=normalize_key)
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
