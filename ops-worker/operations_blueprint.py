"""Flask transport boundary for the recent operations route."""

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from flask import Blueprint, jsonify, request

from operations_route import handle_operations_recent


def create_operations_blueprint(
    *,
    get_db_engine: Callable[[], Optional[Any]],
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    sanitize_limit: Callable[[Optional[str]], int],
    sanitize_offset: Callable[[Optional[str]], int],
    sql_text: Callable[[str], Any],
    rows_to_operations: Callable[[Sequence[Mapping[str, Any]]], List[Dict[str, Any]]],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Blueprint:
    """Create the operations Blueprint with explicit runtime providers."""
    blueprint = Blueprint("operations", __name__)

    @blueprint.get("/api/operations/recent")
    def api_operations_recent():
        return handle_operations_recent(
            request.args,
            db_engine=get_db_engine(),
            find_host=find_host,
            sanitize_limit=sanitize_limit,
            sanitize_offset=sanitize_offset,
            sql_text=sql_text,
            rows_to_operations=rows_to_operations,
            jsonify=jsonify,
            internal_error_response=internal_error_response,
        )

    return blueprint


__all__ = ["create_operations_blueprint"]
