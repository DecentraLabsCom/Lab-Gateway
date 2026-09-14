"""Persistence operations for temporary Guacamole users."""

import re
from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional


_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _validate_session_id(session_id: str) -> str:
    if not session_id or not _SESSION_ID_RE.match(str(session_id)):
        raise ValueError("sessionId is required and must be a safe identifier")
    return str(session_id)


def provision_temporary_user(
    selector: str,
    session_id: str,
    valid_until_epoch: Optional[Any],
    activate: bool = True,
    *,
    engine: Any,
    parse_selector: Callable[[Any], int],
    resolve_connection: Callable[[int], Optional[Mapping[str, Any]]],
    safe_connection_response: Callable[[Mapping[str, Any]], Dict[str, Any]],
    sql_text: Callable[[str], Any],
    date_from_epoch: Callable[[int], str],
    logger: Any,
) -> Dict[str, Any]:
    if not engine:
        raise RuntimeError("Guacamole database not configured")
    connection_id = parse_selector(selector)
    normalized_session_id = _validate_session_id(session_id)
    username = f"dlabs-res-{normalized_session_id}"
    valid_until_date = None
    if valid_until_epoch not in (None, ""):
        valid_until_date = date_from_epoch(int(valid_until_epoch))

    connection = resolve_connection(connection_id)
    if not connection:
        raise ValueError(f"Guacamole connection {connection_id} not found")

    with engine.begin() as conn:
        if conn.dialect.name == "mysql":
            conn.execute(
                sql_text(
                    """
                    INSERT INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    ON DUPLICATE KEY UPDATE name = VALUES(name)
                    """
                ),
                {"username": username},
            )
        else:
            conn.execute(
                sql_text(
                    """
                    INSERT OR IGNORE INTO guacamole_entity (name, type)
                    VALUES (:username, 'USER')
                    """
                ),
                {"username": username},
            )

        entity_id = conn.execute(
            sql_text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            raise RuntimeError("Unable to resolve temporary Guacamole entity")

        if conn.dialect.name == "mysql":
            conn.execute(
                sql_text(
                    """
                    INSERT INTO guacamole_user (entity_id, password_hash, password_date, disabled, expired, valid_until)
                    VALUES (:entity_id, UNHEX(SHA2(UUID(), 256)), UTC_TIMESTAMP(), :disabled, FALSE, :valid_until)
                    ON DUPLICATE KEY UPDATE disabled = VALUES(disabled), expired = FALSE, valid_until = VALUES(valid_until)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )
        else:
            conn.execute(
                sql_text(
                    """
                    INSERT OR REPLACE INTO guacamole_user (entity_id, valid_until, disabled)
                    VALUES (:entity_id, :valid_until, :disabled)
                    """
                ),
                {"entity_id": entity_id, "disabled": not activate, "valid_until": valid_until_date},
            )

        if activate:
            if conn.dialect.name == "mysql":
                conn.execute(
                    sql_text(
                        """
                        INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        ON DUPLICATE KEY UPDATE permission = VALUES(permission)
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
            else:
                conn.execute(
                    sql_text(
                        """
                        INSERT OR REPLACE INTO guacamole_connection_permission (entity_id, connection_id, permission)
                        VALUES (:entity_id, :connection_id, 'READ')
                        """
                    ),
                    {"entity_id": entity_id, "connection_id": connection_id},
                )
        else:
            conn.execute(
                sql_text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"),
                {"entity_id": entity_id},
            )

    logger.info("Provisioned temporary Guacamole user")
    return {
        "success": True,
        "sessionId": normalized_session_id,
        "username": username,
        "connection": safe_connection_response(connection),
    }


def delete_temporary_user(
    session_id: str,
    *,
    engine: Any,
    sql_text: Callable[[str], Any],
    logger: Any,
) -> bool:
    if not engine:
        raise RuntimeError("Guacamole database not configured")
    normalized_session_id = _validate_session_id(session_id)
    username = f"dlabs-res-{normalized_session_id}"
    with engine.begin() as conn:
        entity_id = conn.execute(
            sql_text("SELECT entity_id FROM guacamole_entity WHERE name = :username AND type = 'USER'"),
            {"username": username},
        ).scalar()
        if entity_id is None:
            return False
        conn.execute(sql_text("DELETE FROM guacamole_connection_permission WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(sql_text("DELETE FROM guacamole_user WHERE entity_id = :entity_id"), {"entity_id": entity_id})
        conn.execute(sql_text("DELETE FROM guacamole_entity WHERE entity_id = :entity_id"), {"entity_id": entity_id})
    logger.info(
        "Deleted temporary Guacamole user %s",
        str(username).replace("\r", "\\r").replace("\n", "\\n"),
    )
    return True


def cleanup_expired_temporary_users(
    *,
    engine: Any,
    sql_text: Callable[[str], Any],
    logger: Any,
) -> int:
    if not engine:
        logger.debug("Skipping Guacamole temp user cleanup: database not configured")
        return 0
    try:
        with engine.begin() as conn:
            if conn.dialect.name == "mysql":
                result = conn.execute(
                    sql_text(
                        """
                        DELETE e FROM guacamole_entity e
                        JOIN guacamole_user u ON u.entity_id = e.entity_id
                        WHERE e.type = 'USER'
                          AND e.name LIKE 'dlabs-res-%'
                          AND u.valid_until IS NOT NULL
                          AND u.valid_until < UTC_DATE()
                        """
                    )
                )
            else:
                result = conn.execute(
                    sql_text(
                        """
                        DELETE FROM guacamole_entity
                        WHERE entity_id IN (
                            SELECT e.entity_id
                            FROM guacamole_entity e
                            JOIN guacamole_user u ON u.entity_id = e.entity_id
                            WHERE e.type = 'USER'
                              AND e.name LIKE 'dlabs-res-%'
                              AND u.valid_until IS NOT NULL
                              AND u.valid_until < CURRENT_DATE
                        )
                        """
                    )
                )
        deleted = result.rowcount if result.rowcount is not None else 0
        if deleted:
            logger.info("Cleaned up %s expired Guacamole temporary users", deleted)
        return deleted
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Guacamole temp user cleanup failed: %s", exc)
        return 0


__all__ = [
    "cleanup_expired_temporary_users",
    "delete_temporary_user",
    "provision_temporary_user",
]
