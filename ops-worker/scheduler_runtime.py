"""Composition adapter for the Ops Worker scheduler."""

from collections.abc import Mapping
from typing import Any


class SchedulerRuntime:
    """Resolve scheduler startup dependencies from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def start_scheduler(self) -> None:
        get = self._get
        environ = get("os").getenv
        return get("_start_scheduler_impl")(
            scheduler_factory=lambda: get("BackgroundScheduler")(daemon=True),
            poll_enabled=environ("OPS_POLL_ENABLED", "false").lower() == "true",
            poll_interval_seconds=int(environ("OPS_POLL_INTERVAL", "60")),
            poll_all_hosts=get("poll_all_hosts"),
            register_reservation_jobs=get("RESERVATION_AUTOMATOR").register,
            cleanup_enabled=get("GUACAMOLE_TEMP_USER_CLEANUP_ENABLED"),
            cleanup_interval_seconds=get("GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS"),
            cleanup_expired_users=get("cleanup_expired_guacamole_temp_users"),
            observation_enabled=get("SESSION_OBSERVATION_OUTBOX_ENABLED"),
            observation_interval_seconds=get("SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS"),
            deliver_observations=get("deliver_session_observation_outbox"),
            revocation_interval_seconds=get("GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS"),
            process_revocations=get("process_guacamole_token_revocations"),
            now=lambda: get("datetime").now(get("timezone").utc),
            logger=get("logging"),
        )


def create_scheduler_runtime(providers: Mapping[str, Any]) -> SchedulerRuntime:
    """Create a scheduler adapter bound to live providers."""
    return SchedulerRuntime(providers)


__all__ = ["SchedulerRuntime", "create_scheduler_runtime"]
