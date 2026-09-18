from unittest.mock import Mock

import worker
from local_mode_route import get_local_mode_flag_path


def test_local_mode_flag_path_contract_preserves_host_override_and_default():
    assert get_local_mode_flag_path({"local_mode_flag_path": r"C:\flags\local-mode.flag"}) == r"C:\flags\local-mode.flag"
    assert get_local_mode_flag_path({}) == r"C:\Lab Station\labstation\data\local-mode.flag"


def test_worker_reexports_local_mode_flag_path_without_changing_contract():
    import worker

    assert worker.get_local_mode_flag_path({}) == r"C:\Lab Station\labstation\data\local-mode.flag"


def test_local_mode_route_contract_requires_host_and_enabled(client):
    missing_host = client.post("/api/hosts/local-mode", json={"enabled": True})
    missing_enabled = client.post("/api/hosts/local-mode", json={"host": "lab-ws-01"})

    assert missing_host.status_code == 400
    assert missing_host.json == {"error": "host is required"}
    assert missing_enabled.status_code == 400
    assert missing_enabled.json == {"error": "enabled is required"}


def test_local_mode_route_contract_returns_not_found_without_remote_call(client, monkeypatch):
    find_host = Mock(return_value=None)
    write_remote_file = Mock()
    remove_remote_file = Mock()
    monkeypatch.setattr(worker.HOSTS, "get", find_host)
    monkeypatch.setattr(worker, "write_remote_file", write_remote_file)
    monkeypatch.setattr(worker, "remove_remote_file", remove_remote_file)

    response = client.post(
        "/api/hosts/local-mode",
        json={"host": "unknown", "enabled": "true"},
    )

    assert response.status_code == 404
    assert response.json == {"error": "host 'unknown' not found"}
    write_remote_file.assert_not_called()
    remove_remote_file.assert_not_called()


def test_local_mode_route_contract_enables_flag_with_legacy_arguments(client, monkeypatch):
    host = {"name": "lab-ws-01", "local_mode_flag_path": r"C:\flags\local-mode.flag"}
    write_remote_file = Mock()
    remove_remote_file = Mock()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    monkeypatch.setattr(worker, "write_remote_file", write_remote_file)
    monkeypatch.setattr(worker, "remove_remote_file", remove_remote_file)

    response = client.post(
        "/api/hosts/local-mode",
        json={"host": "lab-ws-01", "enabled": "yes"},
    )

    assert response.status_code == 200
    assert response.json == {"host": "lab-ws-01", "localModeEnabled": True}
    write_remote_file.assert_called_once_with(
        host,
        r"C:\flags\local-mode.flag",
        "1",
        None,
        None,
        None,
        None,
        None,
    )
    remove_remote_file.assert_not_called()


def test_local_mode_route_contract_disables_flag_with_legacy_arguments(client, monkeypatch):
    host = {"name": "lab-ws-01"}
    write_remote_file = Mock()
    remove_remote_file = Mock()
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    monkeypatch.setattr(worker, "write_remote_file", write_remote_file)
    monkeypatch.setattr(worker, "remove_remote_file", remove_remote_file)

    response = client.post(
        "/api/hosts/local-mode",
        json={"host": "lab-ws-01", "enabled": False},
    )

    assert response.status_code == 200
    assert response.json == {"host": "lab-ws-01", "localModeEnabled": False}
    remove_remote_file.assert_called_once_with(
        host,
        r"C:\Lab Station\labstation\data\local-mode.flag",
        None,
        None,
        None,
        None,
        None,
    )
    write_remote_file.assert_not_called()


def test_local_mode_route_contract_hides_remote_errors(client, monkeypatch):
    host = {"name": "lab-ws-01"}
    monkeypatch.setattr(worker.HOSTS, "get", Mock(return_value=host))
    monkeypatch.setattr(
        worker,
        "write_remote_file",
        Mock(side_effect=RuntimeError("winrm password leaked in detail")),
    )

    response = client.post(
        "/api/hosts/local-mode",
        json={"host": "lab-ws-01", "enabled": True},
        headers={"X-Request-ID": "local-mode-1"},
    )

    assert response.status_code == 500
    assert response.json == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "local-mode-1",
    }
    assert "winrm password leaked in detail" not in response.get_data(as_text=True)
