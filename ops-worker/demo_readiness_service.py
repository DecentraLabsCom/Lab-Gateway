"""Runtime checks for the optional demo binding exposed by health."""

import re
from typing import Any, Callable, Dict, Optional


_DEMO_USER_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")


def build_demo_readiness(
    *,
    demo_lab_id: Any,
    demo_connection_id: Any,
    demo_user: Any,
    max_age_seconds: int,
    guacamole_db_engine: Optional[Any],
    db_engine: Optional[Any],
    find_host_by_lab: Callable[[str], Optional[Dict[str, Any]]],
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]],
    to_utc: Callable[[Any], Any],
    sql_text: Callable[[str], Any],
    now: Callable[[], Any],
    logger: Any,
) -> Dict[str, Any]:
    """Validate the configured demo connection and current Station state."""
    raw_lab_id = str(demo_lab_id or "").strip()
    raw_connection_id = str(demo_connection_id or "").strip()
    username = str(demo_user or "")
    result: Dict[str, Any] = {
        "status": "disabled",
        "checks": {
            "connection": False,
            "principal": False,
            "permission": False,
            "physical_host": False,
        },
    }
    if not raw_lab_id and not raw_connection_id:
        return result

    if (
        not raw_lab_id.isdigit()
        or not raw_connection_id.isdigit()
        or int(raw_connection_id) <= 0
        or not username
        or not _DEMO_USER_RE.fullmatch(username)
    ):
        result["status"] = "misconfigured"
        return result

    lab_id = str(int(raw_lab_id))
    connection_id = int(raw_connection_id)
    result["labId"] = lab_id
    result["connectionId"] = connection_id
    if not guacamole_db_engine:
        result["status"] = "unready"
        return result

    try:
        with guacamole_db_engine.begin() as conn:
            connection_exists = int(conn.execute(
                sql_text("SELECT COUNT(*) FROM guacamole_connection WHERE connection_id=:connection_id"),
                {"connection_id": connection_id},
            ).scalar_one()) == 1
            principal_exists = int(conn.execute(
                sql_text(
                    """
                    SELECT COUNT(*)
                    FROM guacamole_entity e
                    JOIN guacamole_user u ON u.entity_id = e.entity_id
                    WHERE e.name=:username AND e.type='USER'
                    """
                ),
                {"username": username},
            ).scalar_one()) == 1
            permission_rows = conn.execute(
                sql_text(
                    """
                    SELECT cp.connection_id, cp.permission
                    FROM guacamole_connection_permission cp
                    JOIN guacamole_entity e ON e.entity_id = cp.entity_id
                    WHERE e.name=:username AND e.type='USER'
                    ORDER BY cp.connection_id, cp.permission
                    """
                ),
                {"username": username},
            ).mappings().all()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Demo readiness Guacamole check failed: %s", exc)
        result["status"] = "unready"
        return result

    result["checks"]["connection"] = connection_exists
    result["checks"]["principal"] = principal_exists
    result["checks"]["permission"] = (
        len(permission_rows) == 1
        and int(permission_rows[0]["connection_id"]) == connection_id
        and str(permission_rows[0]["permission"]).upper() == "READ"
    )
    if not connection_exists or not principal_exists or not result["checks"]["permission"]:
        result["status"] = "misconfigured"
        return result

    host = find_host_by_lab(lab_id)
    if not host:
        result["status"] = "misconfigured"
        return result

    heartbeat = None
    if db_engine:
        try:
            with db_engine.begin() as conn:
                heartbeat = fetch_latest_heartbeat(conn, host.get("name", ""))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Demo readiness Station heartbeat check failed: %s", exc)

    if not heartbeat:
        result["status"] = "unready"
        return result
    if heartbeat.get("localSession") or heartbeat.get("localMode"):
        result["status"] = "busy"
        return result

    heartbeat_ts = to_utc(heartbeat.get("timestamp"))
    heartbeat_age = (
        (now() - heartbeat_ts).total_seconds()
        if heartbeat_ts else None
    )
    result["checks"]["physical_host"] = (
        heartbeat.get("ready") is True
        and heartbeat_age is not None
        and 0 <= heartbeat_age <= max_age_seconds
    )
    result["status"] = "ready" if result["checks"]["physical_host"] else "unready"
    return result


__all__ = ["build_demo_readiness"]
