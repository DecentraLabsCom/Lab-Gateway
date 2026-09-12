"""Pure composition of the Ops Worker health response."""

from typing import Any, Dict, Mapping, Optional, Tuple


def build_health_response(
    *,
    hosts_loaded: int,
    db_ok: bool,
    fernet_ok: bool,
    guacamole_schema_ok: bool,
    failed_revocations: Optional[int],
    failed_observations: Optional[int],
    demo: Mapping[str, Any],
) -> Tuple[Dict[str, Any], int]:
    """Return the public health payload and its status code."""
    revocation_queue_ok = failed_revocations == 0
    observation_outbox_ok = failed_observations == 0
    demo_ok = demo.get("status") in ("disabled", "ready")
    healthy = (
        db_ok
        and fernet_ok
        and guacamole_schema_ok
        and revocation_queue_ok
        and observation_outbox_ok
        and demo_ok
    )
    return {
        "status": "ok" if healthy else "degraded",
        "hosts_loaded": hosts_loaded,
        "db": db_ok,
        "ops_secrets_key": fernet_ok,
        "guacamole_schema": guacamole_schema_ok,
        "guacamole_failed_revocations": failed_revocations,
        "guacamole_revocation_queue": revocation_queue_ok,
        "session_observation_failed": failed_observations,
        "session_observation_outbox": observation_outbox_ok,
        "demo": demo,
    }, 200 if healthy else 503


__all__ = ["build_health_response"]
