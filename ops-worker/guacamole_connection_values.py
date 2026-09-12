"""Pure Guacamole selector parsing and response projection helpers."""

import re
from typing import Any, Dict, Pattern


def parse_guacamole_selector(selector: Any, *, selector_pattern: Pattern[str]) -> int:
    """Parse a validated ``guac:id:<connection_id>`` selector."""
    match = selector_pattern.match(str(selector or "").strip())
    if not match:
        raise ValueError("selector must use guac:id:<connection_id>")
    return int(match.group(1))


def safe_connection_response(connection: Dict[str, Any]) -> Dict[str, Any]:
    """Project a Guacamole connection without exposing account details."""
    connection_id = connection.get("id")
    return {
        "id": connection_id,
        "selector": connection.get("selector") or f"guac:id:{connection_id}",
        "name": connection.get("name"),
        "protocol": connection.get("protocol"),
        "hostname": connection.get("hostname"),
        "port": connection.get("port"),
        "warnings": [],
    }
