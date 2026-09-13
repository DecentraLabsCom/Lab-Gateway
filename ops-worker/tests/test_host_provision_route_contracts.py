import errno
from unittest.mock import Mock

import worker


def _connection(connection_id=42):
    return {
        "id": connection_id,
        "name": "Provisionable",
        "protocol": "rdp",
        "hostname": "lab-ws-42",
        "port": "3389",
    }


def _host_config():
    return {
        "name": "lab-ws-42",
        "address": "lab-ws-42",
        "credential_ref": "lab-ws-42",
        "mac": "00:11:22:33:44:55",
    }


def _configure_success(monkeypatch, *, discovery=None, host_config=None, reload_result=(5, None)):
    connection = _connection()
    calls = []
    monkeypatch.setattr(worker, "resolve_guacamole_connection", Mock(return_value=connection))
    monkeypatch.setattr(
        worker,
        "discover_labstation_candidate",
        Mock(return_value=discovery or {"status": "labstation-detected", "checks": {}}),
    )
    monkeypatch.setattr(
        worker,
        "build_provisioned_host",
        lambda payload, received_connection: calls.append(("build", payload, received_connection))
        or (host_config or _host_config(), None),
    )
    monkeypatch.setattr(worker, "HOSTS", Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(
        worker,
        "upsert_dynamic_host",
        lambda host: calls.append(("upsert", host)),
    )
    monkeypatch.setattr(worker, "reload_hosts", Mock(return_value=reload_result))
    monkeypatch.setattr(
        worker,
        "safe_host_inventory_entry",
        lambda host, **kwargs: calls.append(("safe", host, kwargs))
        or {"name": host["name"], "editable": kwargs["editable"]},
    )
    return connection, calls


def test_host_provision_route_contract_requires_connection_id(client, monkeypatch):
    resolve_connection = Mock()
    monkeypatch.setattr(worker, "resolve_guacamole_connection", resolve_connection)

    response = client.post("/api/hosts/provision", json={})

    assert response.status_code == 400
    assert response.json == {"error": "connectionId is required"}
    resolve_connection.assert_not_called()


def test_host_provision_route_contract_accepts_connection_id_alias(client, monkeypatch):
    connection, calls = _configure_success(monkeypatch)

    response = client.post(
        "/api/hosts/provision",
        json={"connection_id": 42, "name": "lab-ws-42"},
    )

    assert response.status_code == 200
    assert response.json == {
        "provisioned": True,
        "hosts": 5,
        "host": {"name": "lab-ws-42", "editable": True},
        "discoveryStatus": "labstation-detected",
    }
    assert calls[0] == ("build", {"connection_id": 42, "name": "lab-ws-42"}, connection)


def test_host_provision_route_contract_returns_not_found_for_unknown_connection(client, monkeypatch):
    resolve_connection = Mock(return_value=None)
    discover = Mock()
    monkeypatch.setattr(worker, "resolve_guacamole_connection", resolve_connection)
    monkeypatch.setattr(worker, "discover_labstation_candidate", discover)

    response = client.post("/api/hosts/provision", json={"connectionId": 404})

    assert response.status_code == 404
    assert response.json == {"error": "Guacamole connection 404 not found"}
    discover.assert_not_called()


def test_host_provision_route_contract_rejects_insufficient_discovery(client, monkeypatch):
    connection = _connection()
    build_host = Mock()
    monkeypatch.setattr(worker, "resolve_guacamole_connection", Mock(return_value=connection))
    monkeypatch.setattr(
        worker,
        "discover_labstation_candidate",
        Mock(return_value={"status": "host-resolves", "checks": {"winrm": False}}),
    )
    monkeypatch.setattr(worker, "build_provisioned_host", build_host)

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 409
    assert response.json == {
        "error": "insufficient discovery signal for ops host provisioning",
        "discovery": {"status": "host-resolves", "checks": {"winrm": False}},
    }
    build_host.assert_not_called()


def test_host_provision_route_contract_uses_discovered_mac_without_mutating_payload(client, monkeypatch):
    discovery = {
        "status": "winrm-reachable",
        "checks": {},
        "opsHostDraft": {"mac": "00:AA:BB:CC:DD:EE"},
    }
    _connection_value, calls = _configure_success(monkeypatch, discovery=discovery)
    payload = {"connectionId": 42, "name": "lab-ws-42", "mac": "  "}

    response = client.post("/api/hosts/provision", json=payload)

    assert response.status_code == 200
    assert calls[0][0] == "build"
    assert calls[0][1] == {
        "connectionId": 42,
        "name": "lab-ws-42",
        "mac": "00:AA:BB:CC:DD:EE",
    }


def test_host_provision_route_contract_maps_build_error_to_400(client, monkeypatch):
    _configure_success(monkeypatch)
    monkeypatch.setattr(worker, "build_provisioned_host", Mock(return_value=(None, "labs are invalid")))
    upsert_host = Mock()
    monkeypatch.setattr(worker, "upsert_dynamic_host", upsert_host)

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 400
    assert response.json == {"error": "labs are invalid"}
    upsert_host.assert_not_called()


def test_host_provision_route_contract_rejects_missing_built_config(client, monkeypatch):
    _configure_success(monkeypatch)
    monkeypatch.setattr(worker, "build_provisioned_host", Mock(return_value=(None, None)))
    upsert_host = Mock()
    monkeypatch.setattr(worker, "upsert_dynamic_host", upsert_host)

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 400
    assert response.json == {"error": "host configuration could not be built"}
    upsert_host.assert_not_called()


def test_host_provision_route_contract_rejects_existing_host(client, monkeypatch):
    connection = _connection()
    host_config = _host_config()
    monkeypatch.setattr(worker, "resolve_guacamole_connection", Mock(return_value=connection))
    monkeypatch.setattr(worker, "discover_labstation_candidate", Mock(return_value={"status": "labstation-detected"}))
    monkeypatch.setattr(worker, "build_provisioned_host", Mock(return_value=(host_config, None)))
    monkeypatch.setattr(worker, "HOSTS", Mock(get=Mock(return_value=host_config)))
    upsert_host = Mock()
    monkeypatch.setattr(worker, "upsert_dynamic_host", upsert_host)

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 409
    assert response.json == {"error": "host lab-ws-42 already exists"}
    upsert_host.assert_not_called()


def test_host_provision_route_contract_maps_catalog_permission_error_to_503(client, monkeypatch):
    _configure_success(monkeypatch)
    monkeypatch.setattr(worker, "upsert_dynamic_host", Mock(side_effect=PermissionError("secret catalog path")))

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 503
    assert response.json == {
        "error": "Ops host catalog is not writable; check the ops-data mount permissions",
        "code": "OPS_DYNAMIC_CONFIG_NOT_WRITABLE",
    }
    assert "secret catalog path" not in response.get_data(as_text=True)


def test_host_provision_route_contract_maps_read_only_catalog_to_503(client, monkeypatch):
    _configure_success(monkeypatch)
    error = OSError("read-only catalog details")
    error.errno = errno.EROFS
    monkeypatch.setattr(worker, "upsert_dynamic_host", Mock(side_effect=error))

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 503
    assert response.json["code"] == "OPS_DYNAMIC_CONFIG_NOT_WRITABLE"
    assert "read-only catalog details" not in response.get_data(as_text=True)


def test_host_provision_route_contract_hides_unexpected_errors(client, monkeypatch):
    _configure_success(monkeypatch)
    monkeypatch.setattr(
        worker,
        "upsert_dynamic_host",
        Mock(side_effect=RuntimeError("secret provisioning details")),
    )

    response = client.post(
        "/api/hosts/provision",
        json={"connectionId": 42},
        headers={"X-Request-ID": "host-provision-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "host-provision-1",
    }
    assert "secret provisioning details" not in response.get_data(as_text=True)


def test_host_provision_route_contract_maps_reload_failure_to_500(client, monkeypatch):
    _configure_success(monkeypatch, reload_result=(5, "invalid catalog"))
    safe_host = Mock()
    monkeypatch.setattr(worker, "safe_host_inventory_entry", safe_host)

    response = client.post("/api/hosts/provision", json={"connectionId": 42})

    assert response.status_code == 500
    assert response.json == {"error": "Hosts configuration reload failed"}
    safe_host.assert_not_called()
