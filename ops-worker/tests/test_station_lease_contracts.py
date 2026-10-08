from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import text

import pytest

from station_lease import (
    StationLeaseContextError,
    build_demo_dispatch_request,
    build_station_dispatch_request,
    resolve_station_dispatch_request,
)


def _reservation(**overrides):
    now = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    return {
        "lab_id": "42",
        "start_time": now,
        "end_time": now + timedelta(hours=1),
        "status": "CONFIRMED",
        **overrides,
    }


def test_reservation_prepare_envelope_is_deterministic_and_server_bounded():
    args = dict(
        reservation_id="0xabc123",
        lab_id="42",
        host_name="station-1",
        command="prepare-session",
        reservation=_reservation(),
    )
    first = build_station_dispatch_request(**args)
    second = build_station_dispatch_request(**args)

    assert first == second
    assert first["context"]["kind"] == "reservation"
    assert first["context"]["generation"] == 0
    assert first["context"]["notBefore"] == "2026-10-08T10:00:00Z"
    assert first["issuedAt"] == "2026-10-08T09:58:00Z"
    assert first["executeBefore"] == "2026-10-08T10:03:00Z"
    assert first["timeoutSeconds"] == 180


def test_reservation_release_requires_generation_and_keeps_stable_identity():
    args = dict(
        reservation_id="0xabc123",
        lab_id="42",
        host_name="station-1",
        command="release-session",
        reservation=_reservation(),
        prepare_generation=7,
    )
    first = build_station_dispatch_request(**args)
    second = build_station_dispatch_request(**args)

    assert first == second
    assert first["context"]["generation"] == 7
    assert first["timeoutSeconds"] == 90
    with pytest.raises(StationLeaseContextError, match="generation"):
        build_station_dispatch_request(**{**args, "prepare_generation": None})


@pytest.mark.parametrize(
    "reservation,lab_id",
    [
        (_reservation(status="CANCELLED"), "42"),
        (_reservation(end_time=datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)), "42"),
        (_reservation(), "43"),
    ],
)
def test_reservation_prepare_rejects_untrusted_or_ineligible_record(reservation, lab_id):
    with pytest.raises(StationLeaseContextError):
        build_station_dispatch_request(
            reservation_id="0xabc123",
            lab_id=lab_id,
            host_name="station-1",
            command="prepare-session",
            reservation=reservation,
        )


def test_demo_lease_uses_token_identity_and_requires_durable_generation_for_release():
    issued = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    expires = issued + timedelta(minutes=15)
    prepared = build_demo_dispatch_request(
        demo_id="demo:jti-123",
        lab_id="42",
        host_name="station-1",
        command="prepare-session",
        issued_at=issued,
        expires_at=expires,
    )
    released = build_demo_dispatch_request(
        demo_id="demo:jti-123",
        lab_id="42",
        host_name="station-1",
        command="release-session",
        issued_at=issued,
        expires_at=expires,
        prepare_generation=1,
        release_issued_at=issued + timedelta(minutes=2),
    )
    assert prepared["context"]["leaseId"] == "demo:jti-123"
    assert prepared["context"]["kind"] == "demo"
    assert released["context"]["generation"] == 1
    assert released["context"]["notBefore"] == "2026-10-08T10:00:00Z"
    assert released["issuedAt"] == "2026-10-08T10:02:00Z"
    assert released["requestId"] != prepared["requestId"]
    with pytest.raises(StationLeaseContextError, match="generation"):
        build_demo_dispatch_request(
            demo_id="demo:jti-123",
            lab_id="42",
            host_name="station-1",
            command="release-session",
            issued_at=issued,
            expires_at=expires,
        )


def test_resolver_reads_reservation_window_and_prepare_generation_from_gateway_database(db_engine):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with db_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO lab_reservations (transaction_hash,user_id,wallet_address,lab_id,start_time,end_time,status,created_at,updated_at) "
            "VALUES ('0xfeed123',1,'0xwallet','42',:start,:end,'CONFIRMED',:start,:start)"
        ), {"start": now, "end": now + timedelta(hours=1)})
        conn.execute(text(
            "INSERT INTO reservation_operations (reservation_id,lab_id,host,action,status,success,payload,created_at) "
            "VALUES ('0xfeed123','42','station-1','prepare','completed',1,:payload,:created)"
        ), {
            "payload": json.dumps({"metadata": {"lease": {"generation": 4}}}),
            "created": now,
        })

    prepare = resolve_station_dispatch_request(
        engine=db_engine,
        sql_text=text,
        reservation_id="0xfeed123",
        lab_id="42",
        host_name="station-1",
        command="prepare-session",
    )
    release = resolve_station_dispatch_request(
        engine=db_engine,
        sql_text=text,
        reservation_id="0xfeed123",
        lab_id="42",
        host_name="station-1",
        command="release-session",
    )

    assert prepare["context"]["generation"] == 0
    assert release["context"]["generation"] == 4
    assert prepare["context"]["expiresAt"] == release["context"]["expiresAt"]


def test_resolver_uses_gateway_token_expiry_and_durable_demo_release_event(db_engine):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with db_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE guacamole_token_revocation_queue (jwt_jti VARCHAR(128), expires_at DATETIME, created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO guacamole_token_revocation_queue (jwt_jti,expires_at,created_at) VALUES ('demo-jti',:expires,:created)"
        ), {"expires": now + timedelta(minutes=15), "created": now})
        conn.execute(text(
            "INSERT INTO reservation_operations (reservation_id,lab_id,host,action,status,success,payload,created_at) "
            "VALUES ('demo:demo-jti','42','station-1','prepare','completed',1,:payload,:created)"
        ), {"payload": json.dumps({"metadata": {"lease": {"generation": 2}}}), "created": now})
        conn.execute(text(
            "INSERT INTO reservation_operations (reservation_id,lab_id,host,action,status,success,payload,created_at) "
            "VALUES ('demo:demo-jti','42','station-1','demo_expiry','completed',1,'{}',:created)"
        ), {"created": now + timedelta(minutes=20)})

    prepare = resolve_station_dispatch_request(
        engine=db_engine,
        sql_text=text,
        reservation_id="demo:demo-jti",
        lab_id="42",
        host_name="station-1",
        command="prepare-session",
    )
    release = resolve_station_dispatch_request(
        engine=db_engine,
        sql_text=text,
        reservation_id="demo:demo-jti",
        lab_id="42",
        host_name="station-1",
        command="release-session",
    )

    assert prepare["context"]["kind"] == "demo"
    assert prepare["context"]["expiresAt"] == release["context"]["expiresAt"]
    assert release["context"]["generation"] == 2
    assert release["context"]["notBefore"] == now.isoformat(timespec="seconds") + "Z"
    assert release["issuedAt"] == (now + timedelta(minutes=20)).isoformat(timespec="seconds") + "Z"
