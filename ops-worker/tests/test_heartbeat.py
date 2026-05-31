import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_api_poll_heartbeat_persists_data(db_engine, client, monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "winrm_user": "user",
        "winrm_pass": "pass",
    }
    worker.HOSTS = worker.HostRegistry({"hosts": [host]})

    heartbeat = {
        "timestamp": "2026-01-01T12:00:00.000Z",
        "summary": {"ready": True},
        "status": {
            "localModeEnabled": True,
            "localSessionActive": False,
        },
        "operations": {
            "lastPowerAction": {"timestamp": "2026-01-01T11:00:00.000Z", "mode": "powerOn"},
        },
    }

    monkeypatch.setattr(worker, "read_remote_file", lambda *args, **kwargs: json.dumps(heartbeat))

    response = client.post(
        "/api/heartbeat/poll",
        json={"host": "lab-ws-01", "include_events": False},
    )

    assert response.status_code == 200
    assert response.json["host"] == "lab-ws-01"
    assert response.json["heartbeat"]["summary"]["ready"] is True
    assert response.json["heartbeat"]["status"]["localModeEnabled"] is True

    with db_engine.connect() as conn:
        host_row = conn.execute(
            text("SELECT id, name, address, mac FROM lab_hosts WHERE name = :name"),
            {"name": "lab-ws-01"},
        ).mappings().first()
        assert host_row is not None
        assert host_row["address"] == "192.168.1.50"

        heartbeat_row = conn.execute(
            text("SELECT local_mode, local_session, raw_json FROM lab_host_heartbeat WHERE host_id = :host_id"),
            {"host_id": host_row["id"]},
        ).mappings().first()
        assert heartbeat_row is not None
        assert bool(heartbeat_row["local_mode"]) is True
        assert bool(heartbeat_row["local_session"]) is False
        raw_json = json.loads(heartbeat_row["raw_json"])
        assert raw_json["timestamp"] == "2026-01-01T12:00:00.000Z"
