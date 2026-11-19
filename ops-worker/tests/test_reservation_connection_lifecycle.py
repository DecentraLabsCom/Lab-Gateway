from datetime import datetime, timedelta

from sqlalchemy import DateTime, text

from reservation_connection_lifecycle import _record_connection_event


def _typed_sql(statement):
    clause = text(statement)
    if "SELECT state, disconnected_at, cycle_id, lab_id" in statement:
        # MySQL returns DATETIME objects for this projection; annotate the
        # SQLite text query with the same result type for deterministic tests.
        return clause.columns(disconnected_at=DateTime())
    return clause


def _event(
    *,
    event,
    sequence,
    connection_id,
    source="guacamole",
    reservation_id="reservation-1",
    lab_id="lab-1",
):
    return {
        "reservationId": reservation_id,
        "labId": lab_id,
        "source": source,
        "connectionId": connection_id,
        "eventId": f"{connection_id}:{sequence}",
        "event": event,
        "sequence": sequence,
    }


def _record(db_engine, observed_at, payload, *, grace_seconds=120):
    return _record_connection_event(
        payload,
        db_engine=db_engine,
        sql_text=_typed_sql,
        now=lambda: observed_at,
        grace_seconds=grace_seconds,
    )


def _lifecycle(db_engine, reservation_id="reservation-1"):
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT state, disconnected_at, cycle_id "
                "FROM reservation_session_lifecycle WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).mappings().one()
    result = dict(row)
    if isinstance(result.get("disconnected_at"), str):
        result["disconnected_at"] = datetime.fromisoformat(result["disconnected_at"])
    return result


def test_disconnect_enters_grace_only_after_all_reservation_sources_disconnect(db_engine):
    start = datetime(2026, 11, 19, 12, 0, 0)

    connected_guac = _record(
        db_engine,
        start,
        _event(event="connected", sequence=1, connection_id="guac-1"),
    )
    connected_fmu = _record(
        db_engine,
        start,
        _event(event="connected", sequence=1, connection_id="fmu-1", source="fmu"),
    )
    guac_disconnected = _record(
        db_engine,
        start + timedelta(seconds=10),
        _event(event="disconnected", sequence=2, connection_id="guac-1"),
    )

    assert connected_guac[0]["state"] == "active"
    assert connected_fmu[0]["state"] == "active"
    assert guac_disconnected[0]["state"] == "active"
    assert guac_disconnected[0]["activeConnections"] == 1
    assert _lifecycle(db_engine)["state"] == "ACTIVE"

    fmu_disconnected_at = start + timedelta(seconds=20)
    fmu_disconnected = _record(
        db_engine,
        fmu_disconnected_at,
        _event(event="disconnected", sequence=2, connection_id="fmu-1", source="fmu"),
    )

    lifecycle = _lifecycle(db_engine)
    assert fmu_disconnected[0]["state"] == "grace"
    assert lifecycle["state"] == "GRACE"
    assert lifecycle["disconnected_at"] == fmu_disconnected_at
    assert lifecycle["cycle_id"]


def test_reconnect_before_grace_deadline_cancels_pending_close(db_engine):
    disconnected_at = datetime(2026, 11, 19, 12, 0, 0)
    _record(
        db_engine,
        disconnected_at - timedelta(minutes=1),
        _event(event="connected", sequence=1, connection_id="guac-1"),
    )
    _record(
        db_engine,
        disconnected_at,
        _event(event="disconnected", sequence=2, connection_id="guac-1"),
    )

    response, status = _record(
        db_engine,
        disconnected_at + timedelta(seconds=119),
        _event(event="connected", sequence=1, connection_id="guac-2"),
    )

    lifecycle = _lifecycle(db_engine)
    assert status == 200
    assert response["state"] == "active"
    assert response["resumePending"] is False
    assert lifecycle["state"] == "ACTIVE"
    assert lifecycle["disconnected_at"] is None


def test_reconnect_at_grace_deadline_is_queued_for_resume_after_close(db_engine):
    disconnected_at = datetime(2026, 11, 19, 12, 0, 0)
    _record(
        db_engine,
        disconnected_at - timedelta(minutes=1),
        _event(event="connected", sequence=1, connection_id="guac-1"),
    )
    _record(
        db_engine,
        disconnected_at,
        _event(event="disconnected", sequence=2, connection_id="guac-1"),
    )

    response, status = _record(
        db_engine,
        disconnected_at + timedelta(seconds=120),
        _event(event="connected", sequence=1, connection_id="guac-2"),
    )

    lifecycle = _lifecycle(db_engine)
    assert status == 200
    assert response["state"] == "closing"
    assert response["resumePending"] is True
    assert lifecycle["state"] == "CLOSING"

    with db_engine.connect() as conn:
        connection = conn.execute(
            text(
                "SELECT state, cycle_id FROM reservation_session_connections "
                "WHERE reservation_id='reservation-1' AND source='guacamole' "
                "AND connection_id='guac-2'"
            )
        ).mappings().one()
    assert connection["state"] == "CONNECTED"
    assert connection["cycle_id"]


def test_duplicate_or_out_of_order_event_is_idempotent(db_engine):
    disconnected_at = datetime(2026, 11, 19, 12, 0, 0)
    _record(
        db_engine,
        disconnected_at - timedelta(minutes=1),
        _event(event="connected", sequence=1, connection_id="guac-1"),
    )
    disconnect = _event(event="disconnected", sequence=2, connection_id="guac-1")
    _record(db_engine, disconnected_at, disconnect)

    duplicate, duplicate_status = _record(
        db_engine,
        disconnected_at + timedelta(seconds=5),
        disconnect,
    )
    stale, stale_status = _record(
        db_engine,
        disconnected_at + timedelta(seconds=6),
        _event(event="connected", sequence=1, connection_id="guac-1"),
    )

    assert duplicate_status == stale_status == 200
    assert duplicate["alreadyRecorded"] is True
    assert stale["alreadyRecorded"] is True
    assert _lifecycle(db_engine)["disconnected_at"] == disconnected_at


def test_event_validation_rejects_unknown_source_and_wrong_sequence(db_engine):
    now = datetime(2026, 11, 19, 12, 0, 0)
    invalid_source, source_status = _record(
        db_engine,
        now,
        _event(event="connected", sequence=1, connection_id="bad-source", source="browser"),
    )
    invalid_sequence, sequence_status = _record(
        db_engine,
        now,
        _event(event="connected", sequence=2, connection_id="bad-sequence"),
    )

    assert source_status == sequence_status == 400
    assert invalid_source["success"] is False
    assert invalid_sequence["success"] is False
