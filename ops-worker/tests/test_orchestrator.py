import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_orchestrator_fetch_candidates_respects_retry_cooldown(db_engine, monkeypatch):
    monkeypatch.setenv("OPS_RESERVATION_RETRY_COOLDOWN", "1")
    orchestrator = worker.ReservationOrchestrator(db_engine, worker.HostRegistry({"hosts": []}))
    now = datetime.now(timezone.utc)
    reservation_id = "0xstartcandidate"

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_users (wallet_address, username, email, created_at, updated_at)"
                " VALUES (:wallet_address, :username, :email, :created_at, :updated_at)"
            ),
            {
                "wallet_address": "0xfeedface",
                "username": "tester",
                "email": "tester@example.com",
                "created_at": now,
                "updated_at": now,
            },
        )
        user_id = conn.execute(
            text("SELECT id FROM auth_users WHERE wallet_address = :wallet_address"),
            {"wallet_address": "0xfeedface"},
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO lab_reservations (transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, status, created_at, updated_at)"
                " VALUES (:transaction_hash, :user_id, :wallet_address, :lab_id, :start_time, :end_time, :status, :created_at, :updated_at)"
            ),
            {
                "transaction_hash": reservation_id,
                "user_id": user_id,
                "wallet_address": "0xfeedface",
                "lab_id": "42",
                "start_time": now + timedelta(seconds=30),
                "end_time": now + timedelta(hours=1),
                "status": "CONFIRMED",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO reservation_operations (reservation_id, lab_id, host, action, status, success, message, payload, created_at)"
                " VALUES (:reservation_id, :lab_id, :host, :action, :status, :success, :message, :payload, :created_at)"
            ),
            {
                "reservation_id": reservation_id,
                "lab_id": "42",
                "host": "lab-ws-01",
                "action": "scheduler:start",
                "status": "failed",
                "success": False,
                "message": "retry recent",
                "payload": "{}",
                "created_at": now,
            },
        )

    with db_engine.begin() as conn:
        candidates = orchestrator._fetch_start_candidates(conn, now)

    assert len(candidates) == 0


def test_orchestrator_scan_once_dispatches_candidates(db_engine, monkeypatch):
    monkeypatch.setenv("OPS_RESERVATION_AUTOMATION", "true")
    monkeypatch.setenv("OPS_RESERVATION_SCAN_INTERVAL", "30")
    monkeypatch.setenv("OPS_RESERVATION_START_LEAD", "120")
    monkeypatch.setenv("OPS_RESERVATION_END_DELAY", "60")
    monkeypatch.setenv("OPS_RESERVATION_LOOKBACK", "21600")
    monkeypatch.setenv("OPS_RESERVATION_RETRY_COOLDOWN", "1")

    orchestrator = worker.ReservationOrchestrator(db_engine, worker.HostRegistry({"hosts": []}))
    now = datetime.now(timezone.utc)

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_users (wallet_address, username, email, created_at, updated_at)"
                " VALUES (:wallet_address, :username, :email, :created_at, :updated_at)"
            ),
            {
                "wallet_address": "0xdeadc0de",
                "username": "tester",
                "email": "tester@example.com",
                "created_at": now,
                "updated_at": now,
            },
        )
        user_id = conn.execute(
            text("SELECT id FROM auth_users WHERE wallet_address = :wallet_address"),
            {"wallet_address": "0xdeadc0de"},
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO lab_reservations (transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, status, created_at, updated_at)"
                " VALUES (:transaction_hash, :user_id, :wallet_address, :lab_id, :start_time, :end_time, :status, :created_at, :updated_at)"
            ),
            {
                "transaction_hash": "0xstart",
                "user_id": user_id,
                "wallet_address": "0xdeadc0de",
                "lab_id": "42",
                "start_time": now + timedelta(seconds=30),
                "end_time": now + timedelta(hours=1),
                "status": "CONFIRMED",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO lab_reservations (transaction_hash, user_id, wallet_address, lab_id, start_time, end_time, status, created_at, updated_at)"
                " VALUES (:transaction_hash, :user_id, :wallet_address, :lab_id, :start_time, :end_time, :status, :created_at, :updated_at)"
            ),
            {
                "transaction_hash": "0xend",
                "user_id": user_id,
                "wallet_address": "0xdeadc0de",
                "lab_id": "42",
                "start_time": now - timedelta(hours=2),
                "end_time": now - timedelta(minutes=2),
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
            },
        )

    with patch.object(orchestrator, "_dispatch_start") as start_dispatch, patch.object(orchestrator, "_dispatch_end") as end_dispatch:
        orchestrator.scan_once()

    assert start_dispatch.call_count == 1
    assert end_dispatch.call_count == 1
