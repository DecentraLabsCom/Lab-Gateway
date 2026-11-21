from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock

import pytest
from sqlalchemy import text

import worker
from reservation_operations import handle_reservation_end, handle_reservation_start


def _insert_reservation(db_engine, reservation_id, *, now, status="ACTIVE", end_delta=timedelta(hours=1)):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lab_reservations "
                "(transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, "
                "status, created_at, updated_at) "
                "VALUES (:reservation_id, 1, :wallet, :lab_id, :start_time, :end_time, :status, :now, :now)"
            ),
            {
                "reservation_id": reservation_id,
                "wallet": "0x1234",
                "lab_id": "42",
                "start_time": now - timedelta(minutes=30),
                "end_time": now + end_delta,
                "status": status,
                "now": now,
            },
        )


def _insert_reservation_window(db_engine, reservation_id, *, start_at, end_at, status):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO lab_reservations "
                "(transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, status, created_at, updated_at) "
                "VALUES (:reservation_id, 1, :wallet, '42', :start_at, :end_at, :status, :now, :now)"
            ),
            {
                "reservation_id": reservation_id,
                "wallet": "0x1234",
                "start_at": start_at.replace(tzinfo=None),
                "end_at": end_at.replace(tzinfo=None),
                "status": status,
                "now": start_at.replace(tzinfo=None),
            },
        )


def _set_reservation_end(db_engine, reservation_id, end_at):
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE lab_reservations SET end_time=:end_at WHERE transaction_hash=:reservation_id"),
            {"reservation_id": reservation_id, "end_at": end_at.replace(tzinfo=None)},
        )


def _disconnect_reservation(client, db_engine, reservation_id, connection_id):
    _post_connection_event(
        client,
        source="guacamole",
        reservation_id=reservation_id,
        event="connected",
        connection_id=connection_id,
        sequence=1,
    )
    _post_connection_event(
        client,
        source="guacamole",
        reservation_id=reservation_id,
        event="disconnected",
        connection_id=connection_id,
        sequence=2,
    )
    with db_engine.connect() as conn:
        disconnected_at = conn.execute(
            text(
                "SELECT disconnected_at FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    if isinstance(disconnected_at, str):
        disconnected_at = datetime.fromisoformat(disconnected_at)
    return disconnected_at.replace(tzinfo=timezone.utc)


def _orchestrator(db_engine, *, host, now, station_status=None, dispatch_end=None):
    orchestrator = worker.ReservationOrchestrator(
        db_engine,
        worker.HostRegistry({"hosts": [host]}),
    )
    orchestrator.enabled = True
    orchestrator.now = lambda: now
    orchestrator.read_station_status = lambda _host: (
        {"exitCode": 0, "stdout": json.dumps(station_status)}
        if station_status is not None
        else None
    )
    orchestrator.resolve_host_by_lab = lambda _lab_id: host
    orchestrator.dispatch_start = Mock(return_value=({"success": True}, 200))
    orchestrator.dispatch_end = dispatch_end or Mock(return_value=({"success": True}, 200))
    orchestrator.record_operation = Mock()
    return orchestrator


def _install_sqlite_status_updates(orchestrator, db_engine):
    # Production uses MySQL's UTC_TIMESTAMP(); this test database is SQLite.
    def update_status(reservation_id, old_status, new_status):
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE lab_reservations SET status=:new_status "
                    "WHERE transaction_hash=:reservation_id AND status=:old_status"
                ),
                {
                    "reservation_id": reservation_id,
                    "old_status": old_status,
                    "new_status": new_status,
                },
            )

    orchestrator._update_status = update_status


def _end_dispatch(events, host):
    def dispatch(payload, **kwargs):
        def mandatory_field(values, *keys):
            for key in keys:
                value = values.get(key)
                if value not in (None, ""):
                    return str(value)
            return None

        response, status = handle_reservation_end(
            payload,
            find_host=lambda _name: host,
            resolve_host_by_lab=lambda _lab_id: host,
            get_mandatory_field=mandatory_field,
            parse_bool=worker.parse_bool,
            execute_power_phase=lambda _reservation_id, _lab_id, _host, phase, _payload: (
                events.append(phase) or {"success": True, "steps": []}
            ),
            perform_command_step=lambda _host, _reservation_id, _lab_id, _action, command, _args, **_kw: (
                events.append(command) is None,
                {"action": command, "success": True},
            ),
            normalize_args=lambda value, default=None: list(value or default or []),
            resolve_station_lease_context=lambda *_args, **_kwargs: {"requestId": "release-1"},
            authoritative_reservation=kwargs.get("authoritative_reservation"),
            reconciliation_attempt=kwargs.get("reconciliation_attempt"),
            reconciliation_only=kwargs.get("reconciliation_only", False),
        )
        return response, status

    return dispatch


def _post_connection_event(client, *, source, reservation_id, event, connection_id, sequence):
    response = client.post(
        "/api/reservation-connections/event",
        json={
            "reservationId": reservation_id,
            "labId": "42",
            "source": source,
            "connectionId": connection_id,
            "eventId": f"{connection_id}:{sequence}",
            "event": event,
            "sequence": sequence,
        },
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["success"] is True


@pytest.mark.parametrize(
    ("source", "station_reports_close"),
    [("guacamole", True), ("fmu", False)],
)
def test_connection_event_reaches_release_phases_through_worker_api_and_scheduler(
    db_engine,
    client,
    monkeypatch,
    source,
    station_reports_close,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_GRACE_SECONDS", "120")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_CLOSE_FALLBACK_SECONDS", "180")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    reservation_id = f"reservation-{source}"
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_reservation(db_engine, reservation_id, now=started_at)

    _post_connection_event(
        client,
        source=source,
        reservation_id=reservation_id,
        event="connected",
        connection_id=f"{source}-connection-1",
        sequence=1,
    )
    _post_connection_event(
        client,
        source=source,
        reservation_id=reservation_id,
        event="disconnected",
        connection_id=f"{source}-connection-1",
        sequence=2,
    )

    with db_engine.connect() as conn:
        disconnected_at = conn.execute(
            text(
                "SELECT disconnected_at FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    if isinstance(disconnected_at, str):
        disconnected_at = datetime.fromisoformat(disconnected_at)
    scan_at = disconnected_at.replace(tzinfo=timezone.utc) + timedelta(seconds=121)

    host = {"name": "station-42", "management_transport": "ssh"}
    station_status = None
    if station_reports_close:
        station_status = {
            "timestamp": scan_at.isoformat(),
            "profile": "dedicated",
            "reservationDisconnectClose": {
                "reservationKey": reservation_id,
                "labId": "42",
                "leaseId": "lease-1",
                "generation": 1,
                "success": True,
                "completedAt": (
                    disconnected_at.replace(tzinfo=timezone.utc) + timedelta(seconds=120)
                ).isoformat(),
                "method": "app-control",
            },
        }

    events = []
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        station_status=station_status,
        dispatch_end=_end_dispatch(events, host),
    )
    orchestrator.scan_once()
    orchestrator.scan_once()

    assert events == ["pre_end", "release-session", "end", "post_end"]
    orchestrator.dispatch_end = Mock()
    orchestrator.scan_once()
    orchestrator.dispatch_end.assert_not_called()

    with db_engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
        reservation_status = conn.execute(
            text("SELECT status FROM lab_reservations WHERE transaction_hash=:reservation_id"),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert state == "RELEASED"
    assert reservation_status == "ACTIVE"

    _post_connection_event(
        client,
        source=source,
        reservation_id=reservation_id,
        event="connected",
        connection_id=f"{source}-after-early-release",
        sequence=1,
    )
    resume_at = datetime.now(timezone.utc)
    orchestrator.now = lambda: resume_at
    orchestrator.scan_once()

    orchestrator.dispatch_start.assert_called_once()
    assert orchestrator.dispatch_start.call_args.args[0]["actor"] == "reservation-reconnect"
    with db_engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
        reservation_status = conn.execute(
            text("SELECT status FROM lab_reservations WHERE transaction_hash=:reservation_id"),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert state == "ACTIVE"
    assert reservation_status == "ACTIVE"


def test_no_show_without_connection_event_still_releases_at_reservation_end(
    db_engine,
    monkeypatch,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")
    now = datetime.now(timezone.utc)
    reservation_id = "reservation-no-show"
    _insert_reservation(
        db_engine,
        reservation_id,
        now=now.replace(tzinfo=None),
        status="CONFIRMED",
        end_delta=timedelta(seconds=-1),
    )
    host = {"name": "station-42", "management_transport": "ssh"}
    orchestrator = _orchestrator(db_engine, host=host, now=now)

    orchestrator.scan_once()

    orchestrator.dispatch_end.assert_called_once()
    assert orchestrator.dispatch_end.call_args.args[0]["reservationId"] == reservation_id


def test_station_close_fallback_runs_at_three_minutes_only_after_fresh_idle_status(
    db_engine,
    client,
    monkeypatch,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_GRACE_SECONDS", "120")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_CLOSE_FALLBACK_SECONDS", "180")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    reservation_id = "reservation-station-fallback"
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_reservation(db_engine, reservation_id, now=started_at)
    _post_connection_event(
        client,
        source="guacamole",
        reservation_id=reservation_id,
        event="connected",
        connection_id="guac-fallback-1",
        sequence=1,
    )
    _post_connection_event(
        client,
        source="guacamole",
        reservation_id=reservation_id,
        event="disconnected",
        connection_id="guac-fallback-1",
        sequence=2,
    )

    with db_engine.connect() as conn:
        disconnected_at = conn.execute(
            text(
                "SELECT disconnected_at FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    if isinstance(disconnected_at, str):
        disconnected_at = datetime.fromisoformat(disconnected_at)
    disconnected_at = disconnected_at.replace(tzinfo=timezone.utc)

    scan_at = disconnected_at + timedelta(seconds=179)
    status = {
        "timestamp": scan_at.isoformat(),
        "profile": "dedicated",
        "localModeEnabled": False,
        "sessions": {
            "queryOk": True,
            "remoteClientStateKnown": True,
            "remoteClientConnected": True,
            "localSessionActive": False,
            "remoteLabUserSessionIds": ["rdp-session-1"],
        },
    }
    host = {"name": "station-42", "management_transport": "ssh"}
    events = []
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        station_status=status,
        dispatch_end=_end_dispatch(events, host),
    )
    status_payload = {"value": status}
    orchestrator.now = lambda: scan_at
    orchestrator.read_station_status = lambda _host: {
        "exitCode": 0,
        "stdout": json.dumps(status_payload["value"]),
    }

    orchestrator.scan_once()
    assert events == []

    scan_at = disconnected_at + timedelta(seconds=180)
    status_payload["value"] = {
        **status_payload["value"],
        "timestamp": scan_at.isoformat(),
        "sessions": {
            **status_payload["value"]["sessions"],
            "remoteClientConnected": False,
        },
    }
    orchestrator.scan_once()

    assert events == ["pre_end", "release-session", "end", "post_end"]
    with db_engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert state == "RELEASED"


def test_scheduled_end_preempts_missing_station_close_fallback_near_reservation_end(
    db_engine,
    client,
    monkeypatch,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_GRACE_SECONDS", "120")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_CLOSE_FALLBACK_SECONDS", "180")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    reservation_id = "reservation-end-before-disconnect-fallback"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_reservation(db_engine, reservation_id, now=now, status="ACTIVE")
    disconnected_at = _disconnect_reservation(
        client,
        db_engine,
        reservation_id,
        "guac-end-before-fallback",
    )
    scheduled_end = disconnected_at + timedelta(minutes=4)
    _set_reservation_end(db_engine, reservation_id, scheduled_end)

    host = {"name": "station-42", "management_transport": "ssh"}
    events = []
    scan_at = disconnected_at + timedelta(seconds=120)
    status_payload = {
        "value": {
            "timestamp": scan_at.isoformat(),
            "profile": "dedicated",
            "localModeEnabled": False,
            "sessions": {
                "queryOk": True,
                "remoteClientStateKnown": True,
                "remoteClientConnected": True,
                "localSessionActive": False,
                "remoteLabUserSessionIds": ["rdp-session-1"],
            },
        }
    }
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        station_status=status_payload["value"],
        dispatch_end=_end_dispatch(events, host),
    )
    orchestrator.now = lambda: scan_at
    orchestrator.read_station_status = lambda _host: {
        "exitCode": 0,
        "stdout": json.dumps(status_payload["value"]),
    }
    _install_sqlite_status_updates(orchestrator, db_engine)

    # Station still sees the disconnected XRDP session. The reservation has
    # two minutes left, so neither its normal end nor the fallback is due.
    orchestrator.scan_once()
    assert events == []

    # The fallback deadline arrives with only one minute left. Preserve the
    # scheduled reservation end as the owner of release when it is within the
    # Station disconnect grace.
    scan_at = disconnected_at + timedelta(seconds=180)
    status_payload["value"]["timestamp"] = scan_at.isoformat()
    status_payload["value"]["sessions"]["remoteClientConnected"] = False
    orchestrator.scan_once()
    assert events == []

    # The scheduled reservation end releases the station even though Station
    # never reported close.
    scan_at = scheduled_end
    status_payload["value"]["timestamp"] = scan_at.isoformat()
    orchestrator.scan_once()
    assert events == ["pre_end", "release-session", "end", "post_end"]

    # Make the fallback conditions true after completion. The reservation
    # must not be released a second time.
    scan_at = disconnected_at + timedelta(seconds=300)
    status_payload["value"]["timestamp"] = scan_at.isoformat()
    status_payload["value"]["sessions"].update(
        {"remoteClientConnected": False, "remoteLabUserSessionIds": []}
    )
    orchestrator.scan_once()
    assert events == ["pre_end", "release-session", "end", "post_end"]
    with db_engine.connect() as conn:
        reservation_status = conn.execute(
            text("SELECT status FROM lab_reservations WHERE transaction_hash=:reservation_id"),
            {"reservation_id": reservation_id},
        ).scalar_one()
        lifecycle_state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert reservation_status == "COMPLETED"
    assert lifecycle_state == "ENDED"


@pytest.mark.parametrize("seconds_until_end", [30, 119])
def test_disconnect_with_less_than_two_minutes_left_uses_scheduled_end(
    db_engine,
    client,
    monkeypatch,
    seconds_until_end,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_GRACE_SECONDS", "120")
    monkeypatch.setenv("OPS_RESERVATION_DISCONNECT_CLOSE_FALLBACK_SECONDS", "180")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    reservation_id = f"reservation-short-disconnect-{seconds_until_end}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_reservation(db_engine, reservation_id, now=now, status="ACTIVE")
    disconnected_at = _disconnect_reservation(
        client,
        db_engine,
        reservation_id,
        f"guac-short-disconnect-{seconds_until_end}",
    )
    scheduled_end = disconnected_at + timedelta(seconds=seconds_until_end)
    _set_reservation_end(db_engine, reservation_id, scheduled_end)

    host = {"name": "station-42", "management_transport": "ssh"}
    events = []
    scan_at = scheduled_end - timedelta(seconds=1)
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        station_status={
            "profile": "dedicated",
            "sessions": {
                "queryOk": True,
                "remoteClientStateKnown": True,
                "remoteClientConnected": False,
                "localSessionActive": False,
                "remoteLabUserSessionIds": [],
            },
        },
        dispatch_end=_end_dispatch(events, host),
    )
    orchestrator.now = lambda: scan_at
    _install_sqlite_status_updates(orchestrator, db_engine)

    orchestrator.scan_once()
    assert events == []

    scan_at = scheduled_end
    orchestrator.scan_once()
    assert events == ["pre_end", "release-session", "end", "post_end"]
    with db_engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert state == "ENDED"


def test_first_connection_with_less_than_two_minutes_left_still_ends_at_schedule(
    db_engine,
    client,
    monkeypatch,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    reservation_id = "reservation-first-connect-near-end"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_reservation(db_engine, reservation_id, now=now, status="ACTIVE")
    _post_connection_event(
        client,
        source="guacamole",
        reservation_id=reservation_id,
        event="connected",
        connection_id="guac-first-connect-near-end",
        sequence=1,
    )
    with db_engine.connect() as conn:
        connected_at = conn.execute(
            text(
                "SELECT connected_at FROM reservation_session_connections "
                "WHERE reservation_id=:reservation_id AND connection_id=:connection_id"
            ),
            {
                "reservation_id": reservation_id,
                "connection_id": "guac-first-connect-near-end",
            },
        ).scalar_one()
    if isinstance(connected_at, str):
        connected_at = datetime.fromisoformat(connected_at)
    connected_at = connected_at.replace(tzinfo=timezone.utc)
    scheduled_end = connected_at + timedelta(seconds=90)
    _set_reservation_end(db_engine, reservation_id, scheduled_end)

    host = {"name": "station-42", "management_transport": "ssh"}
    events = []
    scan_at = scheduled_end - timedelta(seconds=1)
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        dispatch_end=_end_dispatch(events, host),
    )
    orchestrator.now = lambda: scan_at
    _install_sqlite_status_updates(orchestrator, db_engine)

    orchestrator.scan_once()
    assert events == []

    scan_at = scheduled_end
    orchestrator.scan_once()
    assert events == ["pre_end", "release-session", "end", "post_end"]
    with db_engine.connect() as conn:
        state = conn.execute(
            text(
                "SELECT state FROM reservation_session_lifecycle "
                "WHERE reservation_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        ).scalar_one()
    assert state == "ENDED"


def test_contiguous_reservation_start_retries_after_previous_lease_is_released(
    db_engine,
    monkeypatch,
):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_START_LEAD", "120")
    monkeypatch.setenv("OPS_RESERVATION_RETRY_COOLDOWN", "60")
    monkeypatch.setenv("RESERVATION_PROJECTION_URL", "")

    next_start = datetime.now(timezone.utc).replace(microsecond=0)
    previous_id = "reservation-immediately-before"
    next_id = "reservation-immediately-after"
    _insert_reservation_window(
        db_engine,
        previous_id,
        start_at=next_start - timedelta(hours=1),
        end_at=next_start,
        status="ACTIVE",
    )
    _insert_reservation_window(
        db_engine,
        next_id,
        start_at=next_start,
        end_at=next_start + timedelta(hours=1),
        status="CONFIRMED",
    )

    host = {"name": "station-42", "management_transport": "ssh"}
    prior_lease = {"active": True}
    timeline = []

    def dispatch_start(payload, **_kwargs):
        reservation_id = payload["reservationId"]

        def execute_power_phase(_reservation_id, _lab_id, _host, phase, _payload):
            timeline.append(f"{reservation_id}:{phase}")
            return {"success": True, "steps": []}

        def perform_wake_step(_host, _reservation_id, _lab_id, _options):
            timeline.append(f"{reservation_id}:wake")
            return True, {"action": "wake", "success": True}

        def perform_command_step(_host, command_reservation_id, _lab_id, _action, command, _args, **_kwargs):
            assert command == "prepare-session"
            blocked = prior_lease["active"]
            timeline.append(
                f"{command_reservation_id}:prepare-session:{'lease-conflict' if blocked else 'ok'}"
            )
            return not blocked, {
                "action": command,
                "success": not blocked,
                **({"code": "STATION_LEASE_CONFLICT"} if blocked else {}),
            }

        return handle_reservation_start(
            payload,
            find_host=lambda _name: host,
            resolve_host_by_lab=lambda _lab_id: host,
            get_mandatory_field=lambda values, *keys: next(
                (str(values[key]) for key in keys if values.get(key) not in (None, "")),
                None,
            ),
            parse_bool=worker.parse_bool,
            execute_power_phase=execute_power_phase,
            perform_wake_step=perform_wake_step,
            perform_command_step=perform_command_step,
            normalize_args=lambda value, default=None: list(value or default or []),
            resolve_station_lease_context=lambda *_args, **_kwargs: {"requestId": "prepare-next"},
        )

    def dispatch_end(payload, **_kwargs):
        reservation_id = payload["reservationId"]
        timeline.extend(
            [
                f"{reservation_id}:pre_end",
                f"{reservation_id}:release-session",
                f"{reservation_id}:end",
                f"{reservation_id}:post_end",
            ]
        )
        prior_lease["active"] = False
        return {"success": True}, 200

    scan_at = next_start - timedelta(seconds=120)
    orchestrator = _orchestrator(
        db_engine,
        host=host,
        now=scan_at,
        dispatch_end=dispatch_end,
    )
    orchestrator.now = lambda: scan_at
    orchestrator.dispatch_start = dispatch_start
    _install_sqlite_status_updates(orchestrator, db_engine)

    # pre_start runs while the prior reservation still owns the station lease;
    # Station rejects Prepare, but later start energy phases still run.
    orchestrator.scan_once()
    assert timeline == [
        f"{next_id}:pre_start",
        f"{next_id}:wake",
        f"{next_id}:start",
        f"{next_id}:prepare-session:lease-conflict",
        f"{next_id}:post_start",
    ]

    # At the shared boundary, the current scheduler retries the next start
    # before dispatching the previous end. That Prepare is also rejected; the
    # previous reservation still receives its scheduled energy cleanup.
    scan_at = next_start
    orchestrator.scan_once()
    assert timeline[5:14] == [
        f"{next_id}:pre_start",
        f"{next_id}:wake",
        f"{next_id}:start",
        f"{next_id}:prepare-session:lease-conflict",
        f"{next_id}:post_start",
        f"{previous_id}:pre_end",
        f"{previous_id}:release-session",
        f"{previous_id}:end",
        f"{previous_id}:post_end",
    ]

    # After the normal retry cooldown, the next reservation can acquire the
    # released station lease and complete its start phases.
    scan_at = next_start + timedelta(seconds=61)
    orchestrator.scan_once()
    assert timeline[14:] == [
        f"{next_id}:pre_start",
        f"{next_id}:wake",
        f"{next_id}:start",
        f"{next_id}:prepare-session:ok",
        f"{next_id}:post_start",
    ]
    with db_engine.connect() as conn:
        statuses = dict(
            conn.execute(
                text(
                    "SELECT transaction_hash, status FROM lab_reservations "
                    "WHERE transaction_hash IN (:previous_id, :next_id)"
                ),
                {"previous_id": previous_id, "next_id": next_id},
            ).all()
        )
    assert statuses == {previous_id: "COMPLETED", next_id: "ACTIVE"}
