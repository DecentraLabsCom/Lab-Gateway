"""Flask transport boundary for the reservation timeline route."""

from typing import Any, Callable, Dict, Optional

from flask import Blueprint, jsonify, request

from timeline_route import handle_reservation_timeline


def create_timeline_blueprint(
    *,
    get_db_engine: Callable[[], Optional[Any]],
    sanitize_limit: Callable[[Optional[str]], int],
    sanitize_offset: Callable[[Optional[str]], int],
    build_timeline: Callable[[str, int, int], Dict[str, Any]],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Blueprint:
    """Create the reservation timeline Blueprint with explicit providers."""
    blueprint = Blueprint("timeline", __name__)

    @blueprint.get("/api/reservations/timeline")
    def api_reservation_timeline():
        return handle_reservation_timeline(
            request.args,
            db_engine=get_db_engine(),
            sanitize_limit=sanitize_limit,
            sanitize_offset=sanitize_offset,
            build_timeline=build_timeline,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_timeline_blueprint"]
