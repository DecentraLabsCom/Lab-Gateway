"""Flask transport boundary for reservation and demo lifecycle routes."""

from typing import Any, Callable, Dict, Tuple

from flask import Blueprint, jsonify, request

from lifecycle_routes import handle_lifecycle_request


LifecycleOperation = Callable[[Any], Tuple[Dict[str, Any], int]]


def create_lifecycle_blueprint(
    *,
    reservation_start: LifecycleOperation,
    reservation_end: LifecycleOperation,
    demo_start: LifecycleOperation,
    demo_event: LifecycleOperation,
    demo_end: LifecycleOperation,
) -> Blueprint:
    """Create the lifecycle Blueprint with explicit operation providers."""
    blueprint = Blueprint("lifecycle", __name__)

    def _handle(operation: LifecycleOperation):
        payload: Any = request.get_json(force=True, silent=True) or {}
        return handle_lifecycle_request(payload, operation=operation, jsonify=jsonify)

    @blueprint.post("/api/reservations/start")
    def api_reservation_start():
        return _handle(reservation_start)

    @blueprint.post("/api/reservations/end")
    def api_reservation_end():
        return _handle(reservation_end)

    @blueprint.post("/api/demo/start")
    def api_demo_start():
        return _handle(demo_start)

    @blueprint.post("/api/demo/event")
    def api_demo_event():
        return _handle(demo_event)

    @blueprint.post("/api/demo/end")
    def api_demo_end():
        return _handle(demo_end)

    return blueprint


__all__ = ["create_lifecycle_blueprint"]
