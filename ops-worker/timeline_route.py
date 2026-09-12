"""Composition for the reservation timeline HTTP route."""

from typing import Any, Callable, Dict, Mapping, Optional


def handle_reservation_timeline(
    query_params: Mapping[str, Any],
    *,
    db_engine: Optional[Any],
    sanitize_limit: Callable[[Optional[str]], int],
    sanitize_offset: Callable[[Optional[str]], int],
    build_timeline: Callable[[str, int, int], Dict[str, Any]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Build the timeline response while keeping DB orchestration injectable."""
    if not db_engine:
        return jsonify({"error": "Database not configured"}), 500
    reservation_id = query_params.get("reservationId") or query_params.get("reservation_id")
    if not reservation_id:
        return jsonify({"error": "reservationId is required"}), 400
    limit = sanitize_limit(query_params.get("limit"))
    offset = sanitize_offset(query_params.get("offset"))
    try:
        data = build_timeline(str(reservation_id), limit, offset)
    except LookupError:
        return jsonify({"error": "Reservation not found"}), 404
    except RuntimeError as exc:
        return internal_error_response("Timeline error", exc)
    return jsonify(data)


__all__ = ["handle_reservation_timeline"]
