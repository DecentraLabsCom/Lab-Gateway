"""Flask transport boundary for the public health route."""

from typing import Any, Callable, Dict, Optional, Tuple

from flask import Blueprint, jsonify

from health_values import build_health_response as _build_health_response_default


GUACAMOLE_SCHEMA_CHECK = """
SELECT 1
FROM guacamole_entity e
LEFT JOIN guacamole_user u ON u.entity_id = e.entity_id
LEFT JOIN guacamole_connection_permission cp ON cp.entity_id = e.entity_id
LEFT JOIN guacamole_connection c ON c.connection_id = cp.connection_id
LIMIT 1
"""


def create_health_blueprint(
    *,
    get_db_engine: Callable[[], Optional[Any]],
    get_guacamole_db_engine: Callable[[], Optional[Any]],
    database_is_usable: Callable[[Optional[Any], str], bool],
    fernet_key_is_usable: Callable[[], bool],
    demo_readiness: Callable[[], Dict[str, Any]],
    get_hosts_loaded: Callable[[], int],
    build_health_response: Callable[..., Tuple[Dict[str, Any], int]] = _build_health_response_default,
    sql_text: Callable[[str], Any],
    log_warning: Callable[..., None],
) -> Blueprint:
    """Create the public health Blueprint with explicit runtime providers."""
    blueprint = Blueprint("health", __name__)

    @blueprint.get("/health")
    def api_health():
        db_engine = get_db_engine()
        db_ok = database_is_usable(db_engine, "SELECT 1")
        fernet_ok = fernet_key_is_usable()

        guacamole_engine = get_guacamole_db_engine()
        guacamole_schema_ok = database_is_usable(
            guacamole_engine,
            GUACAMOLE_SCHEMA_CHECK,
        )

        failed_revocations = None
        failed_observations = None
        if db_ok and db_engine:
            try:
                with db_engine.connect() as conn:
                    failed_revocations = int(conn.execute(sql_text(
                        "SELECT COUNT(*) FROM guacamole_token_revocation_queue WHERE status = 'FAILED'"
                    )).scalar_one())
                    failed_observations = int(conn.execute(sql_text(
                        "SELECT COUNT(*) FROM gateway_session_observation_outbox WHERE status = 'FAILED'"
                    )).scalar_one())
            except Exception as exc:  # pylint: disable=broad-except
                log_warning("Health durable queue check failed: %s", type(exc).__name__)

        demo = demo_readiness()
        payload, status = build_health_response(
            hosts_loaded=get_hosts_loaded(),
            db_ok=db_ok,
            fernet_ok=fernet_ok,
            guacamole_schema_ok=guacamole_schema_ok,
            failed_revocations=failed_revocations,
            failed_observations=failed_observations,
            demo=demo,
        )
        return jsonify(payload), status

    return blueprint


__all__ = ["create_health_blueprint"]
