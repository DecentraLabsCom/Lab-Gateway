"""Authenticated internal endpoint for reservation connection lifecycle events."""

from typing import Any, Callable, Dict, Tuple

from flask import Blueprint, jsonify, request


ConnectionEvent = Callable[[Any], Tuple[Dict[str, Any], int]]


def create_reservation_connection_blueprint(*, record_event: ConnectionEvent) -> Blueprint:
    blueprint = Blueprint("reservation_connections", __name__)

    @blueprint.post("/api/reservation-connections/event")
    def reservation_connection_event():
        payload = request.get_json(silent=True)
        response, status = record_event(payload)
        return jsonify(response), status

    return blueprint


__all__ = ["create_reservation_connection_blueprint"]
