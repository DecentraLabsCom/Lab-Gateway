import worker


class _Registry:
    def __init__(self, matches=None):
        self.matches = matches or {}
        self.calls = []

    def get(self, name):
        self.calls.append(name)
        return self.matches.get(name)


def _configure(monkeypatch, config, *, registry=None, write=None):
    monkeypatch.setattr(worker, "load_dynamic_config", lambda: config)
    monkeypatch.setattr(worker, "write_dynamic_config", write or (lambda _config: None))
    monkeypatch.setattr(worker, "normalize_match_key", lambda value: str(value or "").strip().lower())
    monkeypatch.setattr(worker, "sanitize_host_name", lambda value, fallback: (value or fallback, None))
    monkeypatch.setattr(worker, "normalize_mac", lambda value: str(value).replace("-", ":"))
    monkeypatch.setattr(worker, "HOSTS", registry or _Registry())


def test_update_dynamic_host_contract_updates_fields_and_preserves_operational_data(monkeypatch):
    current = {
        "name": "lab-01",
        "address": "192.168.1.50",
        "credential_ref": "lab-01",
        "mac": "00:11:22:33:44:55",
        "broadcast": "192.168.1.255",
    }
    config = {"hosts": [current], "version": 2}
    writes = []
    _configure(monkeypatch, config, write=writes.append)

    updated, error = worker.update_dynamic_host(
        "LAB-01",
        {
            "name": "lab-01",
            "mac": "00-22-33-44-55-66",
            "broadcast": "192.168.1.254",
            "heartbeatPath": r"C:\LabStation\heartbeat.json",
        },
    )

    assert error is None
    assert updated == {
        "name": "lab-01",
        "address": "192.168.1.50",
        "credential_ref": "lab-01",
        "mac": "00:22:33:44:55:66",
        "broadcast": "192.168.1.254",
        "heartbeat_path": r"C:\LabStation\heartbeat.json",
        "labstation_exe": r"C:\Lab Station\LabStation.exe",
        "local_mode_flag_path": r"C:\Lab Station\labstation\data\local-mode.flag",
        "events_path": r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl",
    }
    assert config["version"] == 2
    assert writes == [config]


def test_update_dynamic_host_contract_rejects_static_catalog_entry_without_writing(monkeypatch):
    writes = []
    _configure(monkeypatch, {"hosts": [{"name": "dynamic"}]}, write=writes.append)

    updated, error = worker.update_dynamic_host("static", {"name": "renamed"})

    assert updated is None
    assert error == "host is defined in the static catalog; edit ops-worker/hosts.json manually"
    assert writes == []


def test_update_dynamic_host_contract_rejects_rename_collision_without_writing(monkeypatch):
    registry = _Registry({"taken": {"name": "taken"}})
    writes = []
    _configure(
        monkeypatch,
        {"hosts": [{"name": "current", "address": "192.168.1.50"}]},
        registry=registry,
        write=writes.append,
    )

    updated, error = worker.update_dynamic_host("current", {"name": "taken"})

    assert updated is None
    assert error == "host taken already exists"
    assert registry.calls == ["taken"]
    assert writes == []


def test_update_dynamic_host_contract_rejects_invalid_mac_without_writing(monkeypatch):
    writes = []
    _configure(monkeypatch, {"hosts": [{"name": "lab-01", "mac": "00:11:22:33:44:55"}]}, write=writes.append)
    monkeypatch.setattr(worker, "normalize_mac", lambda _value: None)

    updated, error = worker.update_dynamic_host("lab-01", {"mac": "invalid"})

    assert updated is None
    assert error == "mac must use format 00:11:22:33:44:55 or 00-11-22-33-44-55"
    assert writes == []


def test_update_dynamic_host_contract_removes_mac_when_empty(monkeypatch):
    config = {"hosts": [{"name": "lab-01", "mac": "00:11:22:33:44:55"}]}
    writes = []
    _configure(monkeypatch, config, write=writes.append)

    updated, error = worker.update_dynamic_host("lab-01", {"mac": "  "})

    assert error is None
    assert updated == {
        "name": "lab-01",
        "labstation_exe": r"C:\Lab Station\LabStation.exe",
        "local_mode_flag_path": r"C:\Lab Station\labstation\data\local-mode.flag",
        "heartbeat_path": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
        "events_path": r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl",
    }
    assert writes == [config]


def test_update_dynamic_host_contract_rejects_invalid_heartbeat_path_without_writing(monkeypatch):
    writes = []
    _configure(monkeypatch, {"hosts": [{"name": "lab-01"}]}, write=writes.append)

    updated, error = worker.update_dynamic_host("lab-01", {"heartbeatPath": ""})

    assert updated is None
    assert error == "heartbeatPath is required"
    assert writes == []


def test_update_dynamic_host_contract_updates_all_station_paths_and_keeps_them_coherent(monkeypatch):
    config = {"hosts": [{"name": "lab-01"}]}
    writes = []
    _configure(monkeypatch, config, write=writes.append)

    updated, error = worker.update_dynamic_host(
        "lab-01",
        {
            "labstationExe": r"C:\Lab Station\LabStation.exe",
            "localModeFlagPath": r"C:\LabStation\labstation\data\local-mode.flag",
            "heartbeatPath": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
            "eventsPath": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        },
    )

    assert error is None
    assert updated["labstation_exe"] == r"C:\Lab Station\LabStation.exe"
    assert updated["local_mode_flag_path"] == r"C:\Lab Station\labstation\data\local-mode.flag"
    assert updated["events_path"] == r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl"
    assert writes == [config]


def test_update_dynamic_host_contract_propagates_write_failure(monkeypatch):
    failure = PermissionError("catalog is read-only")
    _configure(
        monkeypatch,
        {"hosts": [{"name": "lab-01"}]},
        write=lambda _config: (_ for _ in ()).throw(failure),
    )

    try:
        worker.update_dynamic_host("lab-01", {"name": "lab-01"})
    except PermissionError as exc:
        assert exc is failure
    else:
        raise AssertionError("update_dynamic_host must propagate write failures")
