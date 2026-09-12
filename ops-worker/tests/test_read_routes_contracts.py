import worker


def test_hosts_route_contract_delegates_inventory_payload(client, monkeypatch):
    inventory = {
        "hosts": [{"name": "lab-ws-01"}],
        "guacamoleAvailable": True,
        "guacamoleError": None,
        "guacamoleUnmatched": [],
    }
    calls = []
    monkeypatch.setattr(worker, "build_host_inventory", lambda: calls.append("inventory") or inventory)

    response = client.get("/api/hosts")

    assert response.status_code == 200
    assert response.json == inventory
    assert calls == ["inventory"]


def test_timeline_route_contract_requires_database(client, monkeypatch):
    monkeypatch.setattr(worker, "DB_ENGINE", None)

    response = client.get("/api/reservations/timeline")

    assert response.status_code == 500
    assert response.json == {"error": "Database not configured"}


def test_timeline_route_contract_accepts_snake_case_alias_and_forwards_pagination(client, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "DB_ENGINE", object())
    monkeypatch.setattr(
        worker,
        "build_reservation_timeline",
        lambda reservation_id, limit, offset: calls.append((reservation_id, limit, offset))
        or {"reservationId": reservation_id, "pagination": {"limit": limit, "offset": offset}},
    )

    response = client.get(
        "/api/reservations/timeline?reservation_id=res-1&limit=2&offset=3"
    )

    assert response.status_code == 200
    assert response.json == {
        "reservationId": "res-1",
        "pagination": {"limit": 2, "offset": 3},
    }
    assert calls == [("res-1", 2, 3)]


def test_timeline_route_contract_maps_missing_reservation_to_404(client, monkeypatch):
    monkeypatch.setattr(worker, "DB_ENGINE", object())
    monkeypatch.setattr(
        worker,
        "build_reservation_timeline",
        lambda *_args: (_ for _ in ()).throw(LookupError("not found")),
    )

    response = client.get("/api/reservations/timeline?reservationId=res-1")

    assert response.status_code == 404
    assert response.json == {"error": "Reservation not found"}


def test_timeline_route_contract_hides_runtime_errors(client, monkeypatch):
    monkeypatch.setattr(worker, "DB_ENGINE", object())
    monkeypatch.setattr(
        worker,
        "build_reservation_timeline",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("secret timeline details")),
    )

    response = client.get("/api/reservations/timeline?reservationId=res-1")

    assert response.status_code == 500
    assert response.json["error"] == "Internal server error"
    assert response.json["code"] == "INTERNAL_ERROR"
    assert "secret timeline details" not in response.get_data(as_text=True)
