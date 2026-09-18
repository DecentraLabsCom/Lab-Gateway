from host_registry import HostRegistry


def test_host_registry_stores_station_configuration_without_lab_index():
    first = {"name": "Station-A", "address": "10.0.0.1", "labs": [42, "shared"]}
    second = {"name": "Station-B", "address": "10.0.0.2", "labs": ["shared", 43]}

    registry = HostRegistry({"hosts": [first, second]})

    assert registry.get("station-a") == {"name": "Station-A", "address": "10.0.0.1"}
    assert all("labs" not in host for host in registry.all_hosts())
    assert not hasattr(registry, "lab_index")
    assert not hasattr(registry, "get_by_lab")
    assert registry.count() == 2


def test_host_registry_drops_inline_credentials_and_invalid_entries():
    registry = HostRegistry({
        "hosts": [
            {
                "name": "Station-A",
                "address": "10.0.0.1",
                "winrm_user": "user",
                "winrm_pass": "password",
            },
            {"name": "missing-address"},
        ]
    })

    assert registry.all_hosts() == [{"name": "Station-A", "address": "10.0.0.1"}]


def test_host_registry_repairs_mixed_installation_roots_from_heartbeat():
    registry = HostRegistry({
        "hosts": [{
            "name": "PC-Siemens",
            "address": "10.192.38.82",
            "heartbeat_path": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
            "events_path": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        }]
    })

    host = registry.get("PC-Siemens")
    assert host["labstation_exe"] == r"C:\Lab Station\LabStation.exe"
    assert host["local_mode_flag_path"] == r"C:\Lab Station\labstation\data\local-mode.flag"
    assert host["events_path"] == r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl"
