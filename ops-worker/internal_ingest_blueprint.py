"""Flask transport boundary for authenticated internal ingestion routes."""

from typing import Any, Callable, Mapping

from flask import Blueprint, jsonify, request

from internal_ingest_routes import handle_internal_ingest


def create_internal_ingest_blueprint(
    *,
    ingest_token: Callable[[], str],
    compare_digest: Callable[..., bool],
    enqueue_revocation: Callable[[Mapping[str, Any]], bool],
    enqueue_observation: Callable[[Mapping[str, Any]], bool],
) -> Blueprint:
    """Create both internal ingestion routes with explicit providers."""
    blueprint = Blueprint("internal_ingest", __name__)

    def _handle(
        payload: Any,
        *,
        enqueue: Callable[[Mapping[str, Any]], bool],
        disabled_error: str,
        invalid_error: str,
    ):
        return handle_internal_ingest(
            payload,
            headers=request.headers,
            ingest_token=ingest_token(),
            compare_digest=compare_digest,
            enqueue=enqueue,
            disabled_error=disabled_error,
            invalid_error=invalid_error,
            jsonify=jsonify,
        )

    @blueprint.post("/internal/guacamole-token-revocations")
    def ingest_guacamole_token_revocation():
        return _handle(
            request.get_json(silent=True),
            enqueue=enqueue_revocation,
            disabled_error="Guacamole revocation ingestion is disabled",
            invalid_error="invalid or unavailable revocation",
        )

    @blueprint.post("/internal/session-observations")
    def ingest_session_observation():
        return _handle(
            request.get_json(silent=True),
            enqueue=enqueue_observation,
            disabled_error="session observation ingestion is disabled",
            invalid_error="invalid or unavailable observation",
        )

    return blueprint


__all__ = ["create_internal_ingest_blueprint"]
