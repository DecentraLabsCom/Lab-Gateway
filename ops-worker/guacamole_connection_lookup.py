"""Read-only Guacamole connection lookup helpers."""

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Tuple


def normalize_match_key(value: Optional[Any]) -> str:
    """Normalize a catalog value for case-insensitive host matching."""
    return str(value or "").strip().lower()


def guacamole_name_candidates(
    connection: Dict[str, Any],
    *,
    load_connections: Callable[[], Tuple[List[Dict[str, Any]], Optional[str]]],
    normalize_key: Callable[[Any], str],
) -> List[str]:
    """Return ordered Guacamole name and hostname candidates for a connection."""
    host_key = normalize_key(connection.get("hostname"))
    candidates: List[str] = []
    connections, _ = load_connections()
    for item in connections:
        if normalize_key(item.get("hostname")) != host_key:
            continue
        text = str(item.get("name") or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    for item in connections:
        if normalize_key(item.get("hostname")) != host_key:
            continue
        text = str(item.get("hostname") or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    fallback = str(connection.get("hostname") or connection.get("name") or "").strip()
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates


def resolve_guacamole_connection(
    connection_id: Any,
    *,
    load_connections: Callable[[], Tuple[List[Dict[str, Any]], Optional[str]]],
) -> Optional[Dict[str, Any]]:
    """Resolve a numeric Guacamole connection ID from the current catalog."""
    try:
        wanted = int(connection_id)
    except (TypeError, ValueError):
        return None
    connections, _ = load_connections()
    for connection in connections:
        if connection.get("id") == wanted:
            return connection
    return None
