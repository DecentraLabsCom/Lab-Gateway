import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_api_operations_recent_pagination_and_reservation_filter(db_engine, client):
    worker.HOSTS = worker.HostRegistry({"hosts": [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
    }]})

    now = datetime.now(timezone.utc)
    reservation_a = "0xabc123"
    reservation_b = "0xdef456"

    with db_engine.begin() as conn:
        for i, (reservation_id, action) in enumerate([
            (reservation_a, "wake"),
            (reservation_b, "prepare"),
            (reservation_a, "release"),
        ]):
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
                    "status": "completed",
                    "success": True,
                    "message": f"{action} message",
                    "payload": '{"action": "' + action + '"}',
                    "created_at": now + timedelta(seconds=i),
                },
            )

    response = client.get("/api/operations/recent?limit=2&offset=1")
    assert response.status_code == 200
    assert response.json["pagination"]["limit"] == 2
    assert response.json["pagination"]["offset"] == 1
    assert response.json["pagination"]["returned"] == 2
    assert response.json["pagination"]["hasMore"] is False
    assert len(response.json["operations"]) == 2
    assert response.json["operations"][0]["action"] == "prepare"
    assert response.json["operations"][1]["action"] == "wake"

    reservation_response = client.get(f"/api/operations/recent?reservationId={reservation_a}&limit=10")
    assert reservation_response.status_code == 200
    assert reservation_response.json["pagination"]["total"] == 2
    assert len(reservation_response.json["operations"]) == 2
    assert {op["action"] for op in reservation_response.json["operations"]} == {"wake", "release"}
