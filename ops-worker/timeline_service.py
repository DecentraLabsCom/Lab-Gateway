"""Database-backed reservation timeline projections."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Dict, List, Optional


def sanitize_limit(value: Any, *, default_limit: int, max_limit: int) -> int:
    """Clamp a requested timeline page size to the configured bounds."""
    if value is None:
        return default_limit
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_limit
    return max(1, min(parsed, max_limit))


def sanitize_offset(value: Any) -> int:
    """Normalize a requested timeline offset to a non-negative integer."""
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def fetch_latest_heartbeat(
    connection: Any,
    host_name: str,
    *,
    sql_text: Callable[[str], Any],
    json_loads: Callable[[str], Any],
    to_iso: Callable[[Any], Optional[str]],
) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        sql_text(
            """
            SELECT h.timestamp_utc, h.ready, h.local_mode, h.local_session,
                   h.last_power_action_ts, h.last_power_action_mode,
                   h.last_forced_logoff_ts, h.last_forced_logoff_user,
                   h.raw_json
            FROM lab_host_heartbeat h
            JOIN lab_hosts ho ON ho.id = h.host_id
            WHERE ho.name = :host
            ORDER BY h.timestamp_utc DESC
            LIMIT 1
            """
        ),
        {"host": host_name},
    ).mappings().first()

    if not row:
        return None

    raw = row.get("raw_json")
    parsed_raw = None
    if isinstance(raw, str):
        try:
            parsed_raw = json_loads(raw)
        except ValueError:
            parsed_raw = None

    return {
        "timestamp": to_iso(row.get("timestamp_utc")),
        "ready": bool(row.get("ready")),
        "localMode": bool(row.get("local_mode")),
        "localSession": bool(row.get("local_session")),
        "lastPower": {
            "timestamp": to_iso(row.get("last_power_action_ts")),
            "mode": row.get("last_power_action_mode"),
        },
        "lastForcedLogoff": {
            "timestamp": to_iso(row.get("last_forced_logoff_ts")),
            "user": row.get("last_forced_logoff_user"),
        },
        "raw": parsed_raw,
    }


def summarize_phases(operations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def picker(prefixes: List[str]) -> Optional[Mapping[str, Any]]:
        for entry in reversed(operations):
            action = entry.get("action") or ""
            if any(action.startswith(prefix) for prefix in prefixes):
                return entry
        return None

    return {
        "wake": picker(["wake", "scheduler:start"]),
        "prepare": picker(["prepare"]),
        "release": picker(["release"]),
        "power": picker(["power:"]),
        "schedulerEnd": picker(["scheduler:end"]),
    }


def build_reservation_timeline(
    reservation_id: str,
    limit: int,
    offset: int,
    *,
    engine: Any,
    host_by_lab: Callable[[Any], Optional[Mapping[str, Any]]],
    sql_text: Callable[[str], Any],
    rows_to_operations: Callable[[Sequence[Mapping[str, Any]]], List[Dict[str, Any]]],
    to_iso: Callable[[Any], Optional[str]],
    phase_lookback: int,
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]],
    summarize_phases: Callable[[Sequence[Mapping[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    if not engine:
        raise RuntimeError("Database not configured")

    with engine.begin() as connection:
        reservation = connection.execute(
            sql_text(
                """
                SELECT transaction_hash, lab_id, status, start_time, end_time,
                       wallet_address, created_at, updated_at
                FROM lab_reservations
                WHERE transaction_hash = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).mappings().first()

        if not reservation:
            raise LookupError("Reservation not found")

        lab_id = reservation.get("lab_id")
        host = host_by_lab(lab_id)
        host_name = (host or {}).get("name")

        total_ops = connection.execute(
            sql_text(
                """
                SELECT COUNT(*) as total
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                """
            ),
            {"reservation_id": reservation_id},
        ).scalar()

        operations = connection.execute(
            sql_text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at ASC, id ASC
                LIMIT :limit_value OFFSET :offset_value
                """
            ),
            {
                "reservation_id": reservation_id,
                "limit_value": limit,
                "offset_value": offset,
            },
        ).mappings().all()
        op_entries = rows_to_operations([dict(row) for row in operations])

        phase_rows = connection.execute(
            sql_text(
                """
                SELECT action, status, success, message, payload,
                       response_code, duration_ms, created_at
                FROM reservation_operations
                WHERE reservation_id = :reservation_id
                ORDER BY created_at DESC, id DESC
                LIMIT :phase_limit
                """
            ),
            {"reservation_id": reservation_id, "phase_limit": phase_lookback},
        ).mappings().all()
        phase_entries = rows_to_operations([dict(row) for row in reversed(phase_rows)])

        latest_heartbeat = None
        if host_name:
            latest_heartbeat = fetch_latest_heartbeat(connection, host_name)

        phases = summarize_phases(phase_entries)
        reservation_payload = {
            "reservationId": reservation.get("transaction_hash"),
            "labId": lab_id,
            "status": reservation.get("status"),
            "start": to_iso(reservation.get("start_time")),
            "end": to_iso(reservation.get("end_time")),
            "walletAddress": reservation.get("wallet_address"),
            "createdAt": to_iso(reservation.get("created_at")),
            "updatedAt": to_iso(reservation.get("updated_at")),
        }

        returned_count = len(op_entries)
        total_ops = total_ops or 0
        next_offset = offset + returned_count
        has_more = total_ops > next_offset
        page = (offset // limit) + 1 if limit else 1

        return {
            "reservation": reservation_payload,
            "host": {
                "name": host_name,
                "labId": lab_id,
                "config": host,
            },
            "operations": op_entries,
            "phases": phases,
            "heartbeat": latest_heartbeat,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "page": page,
                "pageSize": limit,
                "returned": returned_count,
                "total": total_ops,
                "hasMore": has_more,
                "nextOffset": next_offset,
            },
        }


__all__ = [
    "build_reservation_timeline",
    "fetch_latest_heartbeat",
    "sanitize_limit",
    "sanitize_offset",
    "summarize_phases",
]
