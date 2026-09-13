"""Composition for authenticated internal ingestion routes."""

from typing import Any, Callable, Mapping

from werkzeug.datastructures import Headers


HeaderCollection = Headers


def handle_internal_ingest(
    payload: Any,
    *,
    headers: Headers,
    ingest_token: str,
    compare_digest: Callable[..., bool],
    enqueue: Callable[[Mapping[str, Any]], bool],
    disabled_error: str,
    invalid_error: str,
    jsonify: Callable[[Any], Any],
) -> Any:
    """Authenticate and enqueue an internal payload without changing responses."""
    if not ingest_token:
        return jsonify({"accepted": False, "error": disabled_error}), 503
    provided = headers.get("X-Gateway-Observation-Token", "")
    if not compare_digest(provided, ingest_token):
        return jsonify({"accepted": False, "error": "unauthorized"}), 401
    if not isinstance(payload, dict) or not enqueue(payload):
        return jsonify({"accepted": False, "error": invalid_error}), 400
    return jsonify({"accepted": True}), 202


__all__ = ["HeaderCollection", "handle_internal_ingest"]
