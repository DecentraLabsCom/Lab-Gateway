import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from sqlalchemy import text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_reservation_start_heartbeat_timeline_e2e(db_engine, client, monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "winrm_user": "user",
        "winrm_pass": "pass",
        "labs": ["42"],
        "heartbeat_path": "heartbeat.json",
        "events_path": "events.jsonl",
    }
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})

    reservation_id = "0xabc123"
    now = datetime.now(timezone.utc)

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
        user_id = conn.execute(
            text("SELECT id FROM auth_users WHERE wallet_address = :wallet_address"),
            {"wallet_address": "0xdeadbeef"},
        ).scalar()
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

    monkeypatch.setattr(worker, "wol_and_wait", lambda *args, **kwargs: (True, 1))
    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        lambda *args, **kwargs: {"exit_code": 0, "stdout": "prepared", "stderr": "", "duration_ms": 42},
    )

    heartbeat = {
        "timestamp": now.isoformat(),
        "summary": {"ready": True},
        "status": {"localModeEnabled": False, "localSessionActive": False},
    }
    last_event = {"event": "session-started", "timestamp": now.isoformat()}

    def fake_read_remote_file(host_arg, path, *args, **kwargs):
        if path == host["heartbeat_path"]:
            return json.dumps(heartbeat)
        if path == host["events_path"]:
            return json.dumps(last_event)
        raise RuntimeError(f"Unexpected path: {path}")

    monkeypatch.setattr(worker, "read_remote_file", fake_read_remote_file)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", lambda lab_id, host_arg, hb: {"disabled": True})

    response = client.post(
        "/api/reservations/start",
        json={
            "reservationId": reservation_id,
            "host": "lab-ws-01",
            "labId": "42",
        },
    )

    assert response.status_code == 200
    assert response.json["success"] is True
    assert len(response.json["steps"]) == 2
    assert response.json["steps"][0]["action"] == "wake"
    assert response.json["steps"][1]["action"] == "prepare"

    response = client.post(
        "/api/heartbeat/poll",
        json={"host": "lab-ws-01", "include_events": True},
    )
    assert response.status_code == 200
    assert response.json["host"] == "lab-ws-01"
    assert response.json["heartbeat"]["summary"]["ready"] is True
    assert response.json["last_event"]["event"] == "session-started"

    response = client.get(
        "/api/reservations/timeline",
        query_string={"reservationId": reservation_id, "limit": 5},
    )
    assert response.status_code == 200
    assert response.json["reservation"]["reservationId"] == reservation_id
    assert response.json["phases"]["wake"]["action"] == "wake"
    assert response.json["phases"]["prepare"]["action"] == "prepare"
    assert response.json["heartbeat"]["ready"] is True


def test_failed_reservation_start_triggers_notification(db_engine, client, monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "winrm_user": "user",
        "winrm_pass": "pass",
        "labs": ["42"],
    }
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})

    reservation_id = "0xfailure123"
    now = datetime.now(timezone.utc)

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
        user_id = conn.execute(
            text("SELECT id FROM auth_users WHERE wallet_address = :wallet_address"),
            {"wallet_address": "0xdeadbeef"},
        ).scalar()
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

    monkeypatch.setattr(worker, "wol_and_wait", lambda *args, **kwargs: (False, 3))
    mock_post = Mock(return_value=Mock(ok=True, status_code=200, text="sent"))
    monkeypatch.setattr(worker.requests, "post", mock_post)

    response = client.post(
        "/api/reservations/start",
        json={
            "reservationId": reservation_id,
            "host": "lab-ws-01",
            "labId": "42",
        },
    )

    assert response.status_code == 502
    assert response.json["success"] is False
    assert response.json["steps"][0]["action"] == "wake"
    assert response.json["steps"][0]["success"] is False
    assert mock_post.called

    with db_engine.connect() as conn:
        notification_row = conn.execute(
            text(
                "SELECT action, status, success, message FROM reservation_operations "
                "WHERE reservation_id = :reservation_id AND action = 'notification'"
            ),
            {"reservation_id": reservation_id},
        ).mappings().first()

    assert notification_row is not None
    assert notification_row["status"] == "completed"
    assert bool(notification_row["success"]) is True


def test_demo_lifecycle_prepares_connects_and_releases_without_onchain_reservation(
    db_engine, client, monkeypatch
):
    host = {
        "name": "demo-station",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "labs": ["42"],
    }
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})
    monkeypatch.setattr(worker, "DEMO_LAB_ID", "42")
    monkeypatch.setattr(worker, "wol_and_wait", lambda *args, **kwargs: (True, 1))
    monkeypatch.setattr(
        worker,
        "run_labstation_command",
        lambda *args, **kwargs: {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 12},
    )

    start = client.post(
        "/api/demo/start",
        json={"demoId": "demo:abc123", "labId": "42", "expiresAt": 900},
    )
    assert start.status_code == 200
    assert start.json["success"] is True
    assert start.json["operationId"] == "demo:abc123"
    assert [step["action"] for step in start.json["steps"]] == ["wake", "prepare"]

    connected = client.post(
        "/api/demo/event",
        json={"demoId": "demo:abc123", "labId": "42", "event": "connected"},
    )
    assert connected.status_code == 200
    assert connected.json["success"] is True

    end = client.post(
        "/api/demo/end",
        json={"demoId": "demo:abc123", "labId": "42", "reason": "expired"},
    )
    assert end.status_code == 200
    assert end.json["success"] is True

    # Cleanup is idempotent and must not invoke release-session twice.
    second_end = client.post(
        "/api/demo/end",
        json={"demoId": "demo:abc123", "labId": "42", "reason": "expired"},
    )
    assert second_end.status_code == 200
    assert second_end.json["alreadyReleased"] is True

    with db_engine.connect() as conn:
        operations = conn.execute(
            text(
                "SELECT action, success FROM reservation_operations "
                "WHERE reservation_id = :demo_id AND action NOT IN ('notification', 'alert') ORDER BY id"
            ),
            {"demo_id": "demo:abc123"},
        ).mappings().all()
        reservations = conn.execute(text("SELECT COUNT(*) FROM lab_reservations")).scalar_one()

    assert [row["action"] for row in operations] == [
        "wake",
        "prepare",
        "demo_start",
        "demo_connection",
        "demo_expiry",
        "release",
        "demo_cleanup",
    ]
    assert all(bool(row["success"]) for row in operations)
    assert reservations == 0


def test_demo_start_failure_attempts_physical_cleanup(db_engine, client, monkeypatch):
    host = {
        "name": "demo-station",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "labs": ["42"],
    }
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})
    monkeypatch.setattr(worker, "DEMO_LAB_ID", "42")
    monkeypatch.setattr(worker, "NOTIFICATION_SERVICE_ENABLED", False)
    monkeypatch.setattr(worker, "wol_and_wait", lambda *args, **kwargs: (False, 3))
    commands = []

    def fake_command(*args, **kwargs):
        commands.append(args[1])
        return {"exit_code": 0, "stdout": "released", "stderr": "", "duration_ms": 5}

    monkeypatch.setattr(worker, "run_labstation_command", fake_command)

    response = client.post(
        "/api/demo/start",
        json={"demoId": "demo:failed", "labId": "42", "expiresAt": 900},
    )

    assert response.status_code == 502
    assert response.json["success"] is False
    assert commands == ["release-session"]

    with db_engine.connect() as conn:
        operations = conn.execute(
            text(
                "SELECT action, success FROM reservation_operations "
                "WHERE reservation_id = :demo_id AND action NOT IN ('notification', 'alert') ORDER BY id"
            ),
            {"demo_id": "demo:failed"},
        ).mappings().all()

    assert [row["action"] for row in operations] == [
        "wake",
        "demo_start",
        "demo_failure",
        "release",
        "demo_cleanup",
    ]
    assert bool(operations[1]["success"]) is False
