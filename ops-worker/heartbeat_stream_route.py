"""Composition for the heartbeat Server-Sent Events HTTP route."""

from typing import Any, Callable, Dict, Iterable, Mapping, Optional


def handle_heartbeat_stream(
    query_params: Mapping[str, Any],
    *,
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    generate_stream: Callable[[Dict[str, Any], bool], Iterable[str]],
    response_factory: Callable[..., Any],
    stream_with_context: Callable[..., Any],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Build the SSE response while leaving Flask route registration in the root."""
    host_name = query_params.get("host")
    include_events = (
        str(query_params.get("include_events", "true")).strip().lower()
        not in ("0", "false", "no", "off")
    )
    if not host_name:
        return jsonify({"error": "host is required"}), 400
    host = find_host(host_name)
    if not host:
        return jsonify({"error": f"host '{host_name}' not found"}), 404
    response = response_factory(
        stream_with_context(generate_stream(host, include_events)),
        content_type="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


__all__ = ["handle_heartbeat_stream"]
