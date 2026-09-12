import worker


def test_guacamole_connection_route_contract_short_circuits_authorization(client, monkeypatch):
    unauthorized = {"success": False, "error": "Unauthorized"}, 401
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: unauthorized)

    response = client.get("/internal/guacamole/connections")

    assert response.status_code == 401
    assert response.json == {"success": False, "error": "Unauthorized"}


def test_guacamole_connection_route_contract_projects_successful_catalog(client, monkeypatch):
    connection = {"id": 7, "name": "RDP Lab", "hostname": "lab-01"}
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(worker, "load_guacamole_connections", lambda: ([connection], None))
    monkeypatch.setattr(
        worker,
        "safe_connection_response",
        lambda value: {"id": value["id"], "name": value["name"]},
    )

    response = client.get("/internal/guacamole/connections")

    assert response.status_code == 200
    assert response.json == {
        "success": True,
        "connections": [{"id": 7, "name": "RDP Lab"}],
    }


def test_guacamole_connection_route_contract_maps_catalog_failure_to_503(client, monkeypatch):
    monkeypatch.setattr(worker, "require_guacamole_provisioner_auth", lambda: None)
    monkeypatch.setattr(
        worker,
        "load_guacamole_connections",
        lambda: ([], "Guacamole connection inventory unavailable"),
    )

    response = client.get("/internal/guacamole/connections")

    assert response.status_code == 503
    assert response.json == {
        "success": False,
        "error": "Guacamole connection inventory unavailable",
    }
