"""Composition for the recent operations HTTP route."""

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence


def handle_operations_recent(
    query_params: Mapping[str, Any],
    *,
    db_engine: Optional[Any],
    find_host: Callable[[Any], Optional[Dict[str, Any]]],
    sanitize_limit: Callable[[Optional[str]], int],
    sanitize_offset: Callable[[Optional[str]], int],
    sql_text: Callable[[str], Any],
    rows_to_operations: Callable[[Sequence[Mapping[str, Any]]], List[Dict[str, Any]]],
    jsonify: Callable[[Any], Any],
    internal_error_response: Callable[[str, BaseException], Any],
) -> Any:
    """Load and project recent operations while preserving route behavior."""
    if not db_engine:
        return jsonify({"error": "Database not configured"}), 500
    limit = sanitize_limit(query_params.get("limit"))
    offset = sanitize_offset(query_params.get("offset"))
    host_name = query_params.get("host")
    reservation_id = query_params.get("reservationId") or query_params.get("reservation_id")

    query_base = "FROM reservation_operations"
    params: Dict[str, Any] = {}
    where_clauses: List[str] = []
    if host_name:
        host = find_host(host_name)
        if not host:
            return jsonify({"error": f"host '{host_name}' not found"}), 404
        where_clauses.append("host = :host")
        params["host"] = host_name
    if reservation_id:
        where_clauses.append("reservation_id = :reservation_id")
        params["reservation_id"] = reservation_id

    if where_clauses:
        query_base += " WHERE " + " AND ".join(where_clauses)

    params["limit_value"] = limit
    params["offset_value"] = offset
    try:
        with db_engine.begin() as conn:
            total = conn.execute(sql_text("SELECT COUNT(*) as total " + query_base), params).scalar() or 0
            rows = conn.execute(
                sql_text(
                    "SELECT reservation_id, lab_id, host, action, status, success, message, payload, response_code, duration_ms, created_at "
                    + query_base
                    + " ORDER BY created_at DESC, id DESC LIMIT :limit_value OFFSET :offset_value"
                ),
                params,
            ).mappings().all()
        returned = len(rows)
        pagination = {
            "limit": limit,
            "offset": offset,
            "returned": returned,
            "total": total,
            "nextOffset": offset + returned,
            "hasMore": total > offset + returned,
            "page": (offset // limit) + 1 if limit else 1,
            "pageSize": limit,
        }
        return jsonify({
            "operations": rows_to_operations([dict(row) for row in rows]),
            "pagination": pagination,
        })
    except Exception as exc:
        return internal_error_response("Failed to load recent operations", exc)


__all__ = ["handle_operations_recent"]
