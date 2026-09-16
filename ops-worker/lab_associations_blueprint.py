"""Flask transport boundary for calculated lab-to-host associations."""

from collections.abc import Callable, Sequence
from typing import Any, Mapping

from flask import Blueprint, jsonify

from lab_associations_route import handle_lab_associations


def create_lab_associations_blueprint(
    *,
    resolve_lab_associations: Callable[[], Sequence[Mapping[str, Any]]],
) -> Blueprint:
    """Create the protected Lab Manager association projection route."""
    blueprint = Blueprint("lab_associations", __name__)

    @blueprint.get("/api/lab-associations")
    def api_lab_associations():
        return handle_lab_associations(
            resolve_lab_associations=resolve_lab_associations,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_lab_associations_blueprint"]
