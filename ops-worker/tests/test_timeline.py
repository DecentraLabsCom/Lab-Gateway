import os
import sys
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_build_reservation_timeline_includes_phases_and_pagination(db_engine):
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "labs": ["42"],
    }]})

    now = datetime.now(timezone.utc)
    reservation_id = "0xabc123"
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_users (wallet_address, username, email, created_at, updated_at)"
                " VALUES (:wallet_address, :username, :email, :created_at, :updated_at)"
            ),
            {
                "wallet_address": "0xdeadbeef",
                "username": "tester",
                "email": "tester@example.com",
                "created_at": now,
                "updated_at": now,
            },
        )
        user_id = conn.execute(text("SELECT id FROM auth_users WHERE wallet_address = :wallet_address"), {"wallet_address": "0xdeadbeef"}).scalar()
        conn.execute(
            text(
                "INSERT INTO lab_reservations (transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, status, created_at, updated_at)"
                " VALUES (:transaction_hash, :user_id, :wallet_address, :lab_id, :start_time, :end_time, :status, :created_at, :updated_at)"
            ),
            {
                "transaction_hash": reservation_id,
                "user_id": user_id,
                "wallet_address": "0xdeadbeef",
                "lab_id": "42",
                "start_time": now,
                "end_time": now + timedelta(hours=1),
                "status": "CONFIRMED",
                "created_at": now,
                "updated_at": now,
            },
        )
        host_id = conn.execute(
            text(
                "INSERT INTO lab_hosts (name, address, mac, created_at, updated_at)"
                " VALUES (:name, :address, :mac, :created_at, :updated_at)"
            ),
            {
                "name": "lab-ws-01",
                "address": "192.168.1.50",
                "mac": "00:11:22:33:44:55",
                "created_at": now,
                "updated_at": now,
            },
        ).lastrowid
        conn.execute(
            text(
                "INSERT INTO lab_host_heartbeat (host_id, timestamp_utc, ready, local_mode, local_session, raw_json, created_at)"
                " VALUES (:host_id, :timestamp_utc, :ready, :local_mode, :local_session, :raw_json, :created_at)"
            ),
            {
                "host_id": host_id,
                "timestamp_utc": now,
                "ready": True,
                "local_mode": False,
                "local_session": False,
                "raw_json": json.dumps({"timestamp": now.isoformat()}),
                "created_at": now,
            },
        )
        actions = [
            ("wake", "completed", True),
            ("prepare", "completed", True),
            ("release", "completed", True),
            ("power:shutdown", "completed", True),
            ("scheduler:end", "completed", True),
        ]
        for index, (action, status, success) in enumerate(actions):
            conn.execute(
                text(
                    "INSERT INTO reservation_operations (reservation_id, lab_id, host, action, status, success, message, payload, created_at)"
                    " VALUES (:reservation_id, :lab_id, :host, :action, :status, :success, :message, :payload, :created_at)"
                ),
                {
                    "reservation_id": reservation_id,
                    "lab_id": "42",
                    "host": "lab-ws-01",
                    "action": action,
                    "status": status,
                    "success": success,
                    "message": f"{action} message",
                    "payload": json.dumps({"action": action}),
                    "created_at": now + timedelta(seconds=index),
                },
            )

    result = worker.build_reservation_timeline(reservation_id, limit=2, offset=0)

    assert result["reservation"]["reservationId"] == reservation_id
    assert result["host"]["name"] == "lab-ws-01"
    assert result["pagination"]["limit"] == 2
    assert result["pagination"]["returned"] == 2
    assert result["pagination"]["hasMore"] is True
    assert result["phases"]["wake"]["action"] == "wake"
    assert result["phases"]["prepare"]["action"] == "prepare"
    assert result["phases"]["release"]["action"] == "release"
    assert result["phases"]["power"]["action"] == "power:shutdown"
    assert result["phases"]["schedulerEnd"]["action"] == "scheduler:end"
    assert result["heartbeat"]["ready"] is True
