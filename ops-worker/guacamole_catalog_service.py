"""Guacamole connection catalog loading with explicit dependencies."""

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Tuple


def load_guacamole_connections(
    engine: Optional[Any],
    *,
    sql_text: Callable[[str], Any],
    logger: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Load Guacamole connections and their non-temporary users."""
    if not engine:
        return [], "Guacamole database not configured"

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                sql_text(
                    """
                    SELECT
                        c.connection_id,
                        c.connection_name,
                        c.protocol,
                        MAX(CASE WHEN p.parameter_name = 'hostname' THEN p.parameter_value END) AS hostname,
                        MAX(CASE WHEN p.parameter_name = 'port' THEN p.parameter_value END) AS port
                    FROM guacamole_connection c
                    LEFT JOIN guacamole_connection_parameter p
                        ON p.connection_id = c.connection_id
                        AND p.parameter_name IN ('hostname', 'port')
                    GROUP BY c.connection_id, c.connection_name, c.protocol
                    ORDER BY c.connection_id ASC
                    """
                )
            ).mappings().all()
            try:
                user_rows = conn.execute(
                    sql_text(
                        """
                        SELECT
                            cp.connection_id,
                            e.name AS username
                        FROM guacamole_connection_permission cp
                        JOIN guacamole_entity e
                            ON e.entity_id = cp.entity_id
                        WHERE cp.permission = 'READ'
                            AND e.type = 'USER'
                            AND e.name NOT LIKE 'dlabs-res-%'
                        ORDER BY cp.connection_id ASC, e.entity_id ASC
                        """
                    )
                ).mappings().all()
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Unable to load Guacamole connection users: %s", exc)
                user_rows = []
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Unable to load Guacamole connections: %s", exc)
        return [], "Guacamole connection inventory unavailable"

    users_by_connection: Dict[Any, List[str]] = {}
    for row in user_rows:
        connection_id = row.get("connection_id")
        username = str(row.get("username") or "").strip()
        if connection_id is not None and username:
            users_by_connection.setdefault(connection_id, []).append(username)

    return [
        {
            "id": row.get("connection_id"),
            "selector": f"guac:id:{row.get('connection_id')}",
            "name": row.get("connection_name"),
            "protocol": row.get("protocol"),
            "hostname": row.get("hostname"),
            "port": row.get("port"),
            "users": users_by_connection.get(row.get("connection_id"), []),
        }
        for row in rows
    ], None
