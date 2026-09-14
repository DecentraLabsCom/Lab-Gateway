"""Flask transport boundary for the heartbeat Server-Sent Events route."""

from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from flask import Blueprint, Response, jsonify, request, stream_with_context as flask_stream_with_context

from heartbeat_stream_route import handle_heartbeat_stream


def create_heartbeat_stream_blueprint(
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    generate_stream: Callable[[Dict[str, Any], bool], Iterable[str]],
    response_factory: Callable[..., Any] = Response,
    stream_with_context: Callable[..., Any] = flask_stream_with_context,
) -> Blueprint:
    """Create the heartbeat SSE Blueprint with explicit runtime providers."""
    blueprint = Blueprint("heartbeat_stream", __name__)

    @blueprint.get("/api/heartbeat/stream")
    def api_stream_heartbeat():
        query_params: Mapping[str, Any] = request.args
        return handle_heartbeat_stream(
            query_params,
            find_host=find_host,
            generate_stream=generate_stream,
            response_factory=response_factory,
            stream_with_context=stream_with_context,
            jsonify=jsonify,
        )

    return blueprint


__all__ = ["create_heartbeat_stream_blueprint"]
