"""Composition for reservation and demo lifecycle HTTP routes."""

from typing import Any, Callable, Dict, Tuple


def handle_lifecycle_request(
    payload: Any,
    *,
    operation: Callable[[Any], Tuple[Dict[str, Any], int]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Forward a lifecycle payload and preserve its response and status code."""
    response, status = operation(payload)
    return jsonify(response), status


__all__ = ["handle_lifecycle_request"]
