"""Composition adapter for the legacy internal ingestion facades."""

from collections.abc import Mapping
from typing import Any


class InternalIngestRuntime:
    """Resolve request, authentication and queue providers from a live namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def _handle(
        self,
        payload: Any,
        *,
        enqueue: Any,
        disabled_error: str,
        invalid_error: str,
    ) -> Any:
        get = self._get
        request = get("request")
        return get("_handle_internal_ingest_impl")(
            payload,
            headers=request.headers,
            ingest_token=get("SESSION_OBSERVATION_INGEST_TOKEN"),
            compare_digest=get("hmac").compare_digest,
            enqueue=enqueue,
            disabled_error=disabled_error,
            invalid_error=invalid_error,
            jsonify=get("jsonify"),
        )

    def ingest_guacamole_token_revocation(self) -> Any:
        """Accept a legacy Guacamole token-revocation observation."""
        get = self._get
        request = get("request")
        return self._handle(
            request.get_json(silent=True),
            enqueue=get("enqueue_guacamole_token_revocation"),
            disabled_error="Guacamole revocation ingestion is disabled",
            invalid_error="invalid or unavailable revocation",
        )

    def ingest_session_observation(self) -> Any:
        """Accept a legacy session observation from the gateway."""
        get = self._get
        request = get("request")
        return self._handle(
            request.get_json(silent=True),
            enqueue=get("enqueue_session_observation"),
            disabled_error="session observation ingestion is disabled",
            invalid_error="invalid or unavailable observation",
        )


def create_internal_ingest_runtime(providers: Mapping[str, Any]) -> InternalIngestRuntime:
    """Create an internal-ingestion adapter bound to live providers."""
    return InternalIngestRuntime(providers)


__all__ = ["InternalIngestRuntime", "create_internal_ingest_runtime"]
