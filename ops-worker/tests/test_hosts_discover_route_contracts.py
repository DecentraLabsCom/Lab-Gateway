import worker


def test_hosts_discover_route_contract_requires_connection_id(client):
    response = client.post("/api/hosts/discover", json={})

    assert response.status_code == 400
    assert response.json == {"error": "connectionId is required"}


def test_hosts_discover_route_contract_accepts_snake_case_connection_id(client, monkeypatch):
    connection = {"id": 7, "name": "RDP Lab", "hostname": "lab-ws-07"}
    calls = []
    monkeypatch.setattr(
        worker,
        "resolve_guacamole_connection",
        lambda connection_id: calls.append(connection_id) or connection,
    )
    discovery = {"status": "labstation-detected", "connection": connection}
    monkeypatch.setattr(
        worker,
        "discover_labstation_candidate",
        lambda connection_arg: calls.append(connection_arg) or discovery,
    )

    response = client.post("/api/hosts/discover", json={"connection_id": 7})

    assert response.status_code == 200
    assert response.json == discovery
    assert calls == [7, connection]


def test_hosts_discover_route_contract_returns_not_found_for_unknown_connection(client, monkeypatch):
    monkeypatch.setattr(worker, "resolve_guacamole_connection", lambda _connection_id: None)

    response = client.post("/api/hosts/discover", json={"connectionId": 999})

    assert response.status_code == 404
    assert response.json == {"error": "Guacamole connection 999 not found"}
