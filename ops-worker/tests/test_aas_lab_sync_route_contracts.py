from unittest.mock import Mock

import worker


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _ConnectionContext(self.connection)


def _install_host(monkeypatch, *, lab_id="lab-1"):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "labs": [lab_id],
    }
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    return host


def test_aas_lab_sync_route_contract_returns_not_found_for_unmapped_lab(client, monkeypatch):
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": []}))
    sync = Mock()
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/aas-admin/lab/missing/sync")

    assert response.status_code == 404
    assert response.json == {"error": "No host mapping found for labId 'missing'"}
    sync.assert_not_called()


def test_aas_lab_sync_route_contract_uses_persisted_heartbeat_by_default(client, monkeypatch):
    host = _install_host(monkeypatch)
    connection = object()
    heartbeat = {"ready": True, "source": "db"}
    calls = []
    monkeypatch.setattr(worker, "DB_ENGINE", _Engine(connection))
    monkeypatch.setattr(
        worker,
        "_fetch_latest_heartbeat",
        lambda received_connection, host_name: calls.append((received_connection, host_name))
        or {"raw": heartbeat},
    )
    monkeypatch.setattr(
        worker.aas_generator,
        "sync_lab_to_basyx",
        lambda lab_id, received_host, received_heartbeat: calls.append(
            (lab_id, received_host, received_heartbeat)
        ) or {"synced": True, "labId": lab_id},
    )

    response = client.post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.json == {"synced": True, "labId": "lab-1"}
    assert calls == [
        (connection, "lab-ws-01"),
        ("lab-1", host, heartbeat),
    ]


def test_aas_lab_sync_route_contract_polls_fresh_heartbeat_when_requested(client, monkeypatch):
    host = _install_host(monkeypatch)
    heartbeat = {"ready": True, "source": "poll"}
    poll = Mock(return_value={"heartbeat": heartbeat})
    sync = Mock(return_value={"synced": True, "labId": "lab-1"})
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    monkeypatch.setattr(worker, "poll_heartbeat", poll)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post(
        "/aas-admin/lab/lab-1/sync",
        json={"includeHeartbeat": "true"},
    )

    assert response.status_code == 200
    assert response.json == {"synced": True, "labId": "lab-1"}
    poll.assert_called_once_with(host, include_events=False)
    sync.assert_called_once_with("lab-1", host, heartbeat)


def test_aas_lab_sync_route_contract_continues_without_fresh_heartbeat_on_poll_error(client, monkeypatch):
    host = _install_host(monkeypatch)
    warning = Mock()
    poll = Mock(side_effect=RuntimeError("secret heartbeat credentials"))
    sync = Mock(return_value={"synced": True, "labId": "lab-1"})
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    monkeypatch.setattr(worker, "poll_heartbeat", poll)
    monkeypatch.setattr(worker.logging, "warning", warning)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post(
        "/aas-admin/lab/lab-1/sync",
        json={"includeHeartbeat": True},
    )

    assert response.status_code == 200
    assert response.json == {"synced": True, "labId": "lab-1"}
    sync.assert_called_once_with("lab-1", host, None)
    assert "secret heartbeat credentials" not in response.get_data(as_text=True)
    warning.assert_called_once()
    assert warning.call_args.args[:2] == (
        "AAS sync: could not poll heartbeat for lab %s: %s",
        "lab-1",
    )


def test_aas_lab_sync_route_contract_continues_without_persisted_heartbeat_on_db_error(client, monkeypatch):
    _install_host(monkeypatch)
    warning = Mock()
    monkeypatch.setattr(worker, "DB_ENGINE", _Engine(object()))
    monkeypatch.setattr(
        worker,
        "_fetch_latest_heartbeat",
        Mock(side_effect=RuntimeError("secret database details")),
    )
    monkeypatch.setattr(worker.logging, "warning", warning)
    sync = Mock(return_value={"synced": True, "labId": "lab-1"})
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.json == {"synced": True, "labId": "lab-1"}
    sync.assert_called_once_with("lab-1", worker.HOSTS.get_by_lab("lab-1"), None)
    assert "secret database details" not in response.get_data(as_text=True)
    warning.assert_called_once()


def test_aas_lab_sync_route_contract_returns_disabled_result_unchanged(client, monkeypatch):
    host = _install_host(monkeypatch)
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    result = {"disabled": True, "reason": "AAS integration disabled"}
    sync = Mock(return_value=result)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.json == result
    sync.assert_called_once_with("lab-1", host, None)


def test_aas_lab_sync_route_contract_maps_sync_error_to_502(client, monkeypatch):
    host = _install_host(monkeypatch)
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    result = {"error": "AAS synchronization failed", "labId": "lab-1"}
    sync = Mock(return_value=result)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 502
    assert response.json == {
        "detail": "AAS synchronization failed",
        "error": "AAS synchronization failed",
        "labId": "lab-1",
    }


def test_aas_lab_sync_route_contract_returns_success_result_unchanged(client, monkeypatch):
    host = _install_host(monkeypatch)
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    result = {"synced": True, "labId": "lab-1", "submodels": ["heartbeat"]}
    sync = Mock(return_value=result)
    monkeypatch.setattr(worker.aas_generator, "sync_lab_to_basyx", sync)

    response = client.post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.json == result
    sync.assert_called_once_with("lab-1", host, None)
