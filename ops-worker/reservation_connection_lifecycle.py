"""Durable connection tracking and disconnect grace for reservations."""

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import re
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SOURCES = frozenset({"guacamole", "fmu"})
_EVENTS = frozenset({"connected", "disconnected", "failed"})


def _identifier(value: Any, field: str) -> Optional[str]:
    normalized = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(normalized):
        return None
    return normalized


def _ensure_lifecycle_row(
    conn: Any,
    *,
    sql_text: Callable[[str], Any],
    reservation_id: str,
    lab_id: str,
    now: datetime,
) -> None:
    if conn.dialect.name == "mysql":
        statement = """
            INSERT INTO reservation_session_lifecycle (reservation_id, lab_id, state, updated_at)
            VALUES (:reservation_id, :lab_id, 'ACTIVE', :now)
            ON DUPLICATE KEY UPDATE reservation_id=VALUES(reservation_id)
        """
    else:
        statement = """
            INSERT INTO reservation_session_lifecycle (reservation_id, lab_id, state, updated_at)
            VALUES (:reservation_id, :lab_id, 'ACTIVE', :now)
            ON CONFLICT(reservation_id) DO NOTHING
        """
    conn.execute(
        sql_text(statement),
        {"reservation_id": reservation_id, "lab_id": lab_id, "now": now},
    )


def _lock_suffix(conn: Any) -> str:
    return " FOR UPDATE" if conn.dialect.name == "mysql" else ""


def _record_connection_event(
    payload: Any,
    *,
    db_engine: Any,
    sql_text: Callable[[str], Any],
    now: Callable[[], datetime],
    grace_seconds: int,
) -> Tuple[Dict[str, Any], int]:
    """Apply one ordered, idempotent connection transition from a trusted edge."""
    if not db_engine:
        return {"success": False, "error": "Reservation connection persistence is unavailable"}, 503
    if not isinstance(payload, Mapping):
        return {"success": False, "error": "invalid reservation connection event"}, 400

    reservation_id = _identifier(payload.get("reservationId"), "reservationId")
    lab_id = _identifier(payload.get("labId"), "labId")
    source = str(payload.get("source") or "").strip().lower()
    connection_id = _identifier(payload.get("connectionId"), "connectionId")
    event_id = _identifier(payload.get("eventId"), "eventId")
    event = str(payload.get("event") or "").strip().lower()
    sequence = payload.get("sequence")
    if (
        not reservation_id
        or not lab_id
        or source not in _SOURCES
        or not connection_id
        or not event_id
        or event not in _EVENTS
        or type(sequence) is not int
        or sequence != (1 if event == "connected" else 2)
    ):
        return {"success": False, "error": "invalid reservation connection event"}, 400

    observed_at = now().replace(tzinfo=None)
    grace_seconds = max(1, min(300, int(grace_seconds)))
    try:
        with db_engine.begin() as conn:
            _ensure_lifecycle_row(
                conn,
                sql_text=sql_text,
                reservation_id=reservation_id,
                lab_id=lab_id,
                now=observed_at,
            )
            suffix = _lock_suffix(conn)
            lifecycle = conn.execute(
                sql_text(
                    """
                    SELECT state, disconnected_at, cycle_id, lab_id
                    FROM reservation_session_lifecycle
                    WHERE reservation_id=:reservation_id
                    """ + suffix
                ),
                {"reservation_id": reservation_id},
            ).mappings().first()
            if not lifecycle or str(lifecycle.get("lab_id") or "") != lab_id:
                return {"success": False, "error": "reservation laboratory binding mismatch"}, 409

            state = str(lifecycle.get("state") or "ACTIVE").upper()
            cycle_id = lifecycle.get("cycle_id")
            if event == "connected" and state == "ENDED":
                return {"success": False, "error": "reservation session has already been released"}, 409

            connection = conn.execute(
                sql_text(
                    """
                    SELECT sequence, event_id, cycle_id
                    FROM reservation_session_connections
                    WHERE reservation_id=:reservation_id
                      AND source=:source AND connection_id=:connection_id
                    """ + suffix
                ),
                {
                    "reservation_id": reservation_id,
                    "source": source,
                    "connection_id": connection_id,
                },
            ).mappings().first()
            if connection and int(connection.get("sequence") or 0) >= sequence:
                return {
                    "success": True,
                    "alreadyRecorded": True,
                    "state": str(lifecycle.get("state") or "ACTIVE").lower(),
                }, 200

            if event == "connected":
                reconnecting_during_grace = state == "GRACE"
                reconnecting_during_release = state in {"CLOSING", "ENDING"}
                if state == "GRACE":
                    disconnected_at = lifecycle.get("disconnected_at")
                    if not isinstance(disconnected_at, datetime):
                        return {"success": False, "error": "reservation disconnect state is invalid"}, 409
                    if observed_at >= disconnected_at + timedelta(seconds=grace_seconds):
                        conn.execute(
                            sql_text(
                                "UPDATE reservation_session_lifecycle "
                                "SET state='CLOSING', updated_at=:now "
                                "WHERE reservation_id=:reservation_id AND state='GRACE'"
                            ),
                            {"reservation_id": reservation_id, "now": observed_at},
                        )
                        state = "CLOSING"
                        reconnecting_during_release = True
                    else:
                        state = "ACTIVE"
                        conn.execute(
                            sql_text(
                                "UPDATE reservation_session_lifecycle "
                                "SET state=:state, disconnected_at=NULL, cycle_id=NULL, updated_at=:now "
                                "WHERE reservation_id=:reservation_id"
                            ),
                            {
                                "reservation_id": reservation_id,
                                "state": state,
                                "now": observed_at,
                            },
                        )
                elif state == "RELEASED":
                    state = "RESUMING"
                    cycle_id = uuid4().hex[:24]
                    conn.execute(
                        sql_text(
                            "UPDATE reservation_session_lifecycle "
                            "SET state=:state, disconnected_at=NULL, cycle_id=:cycle_id, updated_at=:now "
                            "WHERE reservation_id=:reservation_id AND state='RELEASED'"
                        ),
                        {
                            "reservation_id": reservation_id,
                            "state": state,
                            "cycle_id": cycle_id,
                            "now": observed_at,
                        },
                    )

                pending_resume_cycle_id = None
                if reconnecting_during_release:
                    pending_resume_cycle_id = conn.execute(
                        sql_text(
                            "SELECT cycle_id FROM reservation_session_connections "
                            "WHERE reservation_id=:reservation_id AND state='CONNECTED' "
                            "AND cycle_id IS NOT NULL ORDER BY connected_at ASC LIMIT 1"
                        ),
                        {"reservation_id": reservation_id},
                    ).scalar_one_or_none()
                    if not pending_resume_cycle_id:
                        pending_resume_cycle_id = uuid4().hex[:24]

                connection_cycle_id = (
                    cycle_id
                    if state == "RESUMING" or reconnecting_during_grace
                    else pending_resume_cycle_id
                    if reconnecting_during_release
                    else None
                )

                if connection:
                    conn.execute(
                        sql_text(
                            """
                            UPDATE reservation_session_connections
                            SET state='CONNECTED', sequence=:sequence, event_id=:event_id,
                                cycle_id=:cycle_id,
                                connected_at=:now, disconnected_at=NULL, updated_at=:now
                            WHERE reservation_id=:reservation_id
                              AND source=:source AND connection_id=:connection_id
                            """
                        ),
                        {
                            "reservation_id": reservation_id,
                            "source": source,
                            "connection_id": connection_id,
                            "sequence": sequence,
                            "event_id": event_id,
                            "cycle_id": connection_cycle_id,
                            "now": observed_at,
                        },
                    )
                else:
                    conn.execute(
                        sql_text(
                            """
                            INSERT INTO reservation_session_connections (
                                reservation_id, lab_id, source, connection_id,
                                state, sequence, event_id, cycle_id, connected_at, updated_at
                            ) VALUES (
                                :reservation_id, :lab_id, :source, :connection_id,
                                'CONNECTED', :sequence, :event_id, :cycle_id, :now, :now
                            )
                            """
                        ),
                        {
                            "reservation_id": reservation_id,
                            "lab_id": lab_id,
                            "source": source,
                            "connection_id": connection_id,
                            "sequence": sequence,
                            "event_id": event_id,
                            "cycle_id": connection_cycle_id,
                            "now": observed_at,
                        },
                    )
                return {
                    "success": True,
                    "state": state.lower(),
                    "resumePending": reconnecting_during_release,
                }, 200

            if state == "ENDED":
                return {"success": True, "ignored": True, "state": state.lower()}, 200

            connection_cycle_id = connection.get("cycle_id") if connection else None
            connection_state = "FAILED" if event == "failed" else "DISCONNECTED"
            if connection:
                conn.execute(
                    sql_text(
                        """
                        UPDATE reservation_session_connections
                        SET state=:connection_state, sequence=:sequence, event_id=:event_id,
                            disconnected_at=:now, updated_at=:now
                        WHERE reservation_id=:reservation_id
                          AND source=:source AND connection_id=:connection_id
                        """
                    ),
                    {
                        "reservation_id": reservation_id,
                        "source": source,
                        "connection_id": connection_id,
                        "connection_state": connection_state,
                        "sequence": sequence,
                        "event_id": event_id,
                        "now": observed_at,
                    },
                )
            else:
                conn.execute(
                    sql_text(
                        """
                        INSERT INTO reservation_session_connections (
                            reservation_id, lab_id, source, connection_id,
                            state, sequence, event_id, disconnected_at, updated_at
                        ) VALUES (
                            :reservation_id, :lab_id, :source, :connection_id,
                            :connection_state, :sequence, :event_id, :now, :now
                        )
                        """
                    ),
                    {
                        "reservation_id": reservation_id,
                        "lab_id": lab_id,
                        "source": source,
                        "connection_id": connection_id,
                        "sequence": sequence,
                        "event_id": event_id,
                        "connection_state": connection_state,
                        "now": observed_at,
                    },
                )

            active_count = conn.execute(
                sql_text(
                    """
                    SELECT COUNT(*) FROM reservation_session_connections
                    WHERE reservation_id=:reservation_id AND state='CONNECTED'
                    """
                ),
                {"reservation_id": reservation_id},
            ).scalar_one()
            if state in {"CLOSING", "ENDING", "RELEASED"}:
                return {"success": True, "state": state.lower(), "activeConnections": int(active_count)}, 200
            if not active_count:
                preserve_grace = (
                    event == "failed"
                    and state == "RESUMING"
                    and lifecycle.get("disconnected_at") is not None
                )
                if preserve_grace:
                    conn.execute(
                        sql_text(
                            "UPDATE reservation_session_lifecycle "
                            "SET state='RESUMING', updated_at=:now WHERE reservation_id=:reservation_id"
                        ),
                        {"reservation_id": reservation_id, "now": observed_at},
                    )
                elif event != "failed":
                    conn.execute(
                        sql_text(
                            """
                            UPDATE reservation_session_lifecycle
                            SET state='GRACE', disconnected_at=:now, cycle_id=:cycle_id, updated_at=:now
                            WHERE reservation_id=:reservation_id
                            """
                        ),
                        {
                            "reservation_id": reservation_id,
                            "cycle_id": uuid4().hex[:24],
                            "now": observed_at,
                        },
                    )
                    state = "GRACE"
                elif connection_cycle_id and state in {"ACTIVE", "GRACE"}:
                    if state != "GRACE" or lifecycle.get("disconnected_at") is None:
                        conn.execute(
                            sql_text(
                                "UPDATE reservation_session_lifecycle "
                                "SET state='GRACE', disconnected_at=:now, cycle_id=:cycle_id, updated_at=:now "
                                "WHERE reservation_id=:reservation_id"
                            ),
                            {
                                "reservation_id": reservation_id,
                                "cycle_id": uuid4().hex[:24],
                                "now": observed_at,
                            },
                        )
                    state = "GRACE"
            return {"success": True, "state": state.lower(), "activeConnections": int(active_count)}, 200
    except Exception:
        return {"success": False, "error": "reservation connection state could not be recorded"}, 503


__all__ = ["_record_connection_event"]
