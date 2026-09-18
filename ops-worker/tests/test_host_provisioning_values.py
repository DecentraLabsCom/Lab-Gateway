import re

import host_provisioning_values


NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _build(payload, connection=None):
    return host_provisioning_values.build_provisioned_host(
        payload,
        connection or {"hostname": "station.example"},
        sanitize_host_name_fn=lambda value, fallback: host_provisioning_values.sanitize_host_name(
            value,
            fallback,
            name_pattern=NAME_PATTERN,
        ),
        normalize_mac_fn=lambda value: value.replace("-", ":").upper() if value == "AA-BB-CC-DD-EE-FF" else "",
        normalize_trust_ref_fn=lambda value: str(value).lower(),
        default_heartbeat_path=r"C:\LabStation\heartbeat.json",
        default_events_path=r"C:\LabStation\events.jsonl",
    )


def test_host_provisioning_values_builds_secure_defaults_without_lab_bindings():
    host, error = _build({
        "name": "Station-A",
        "labs": "1,2",
        "mac": "AA-BB-CC-DD-EE-FF",
        "broadcast": "192.168.1.255",
    })

    assert error is None
    assert host is not None
    assert host["name"] == "Station-A"
    assert host["winrm_use_ssl"] is True
    assert host["winrm_port"] == 5986
    assert "labs" not in host
    assert host["mac"] == "AA:BB:CC:DD:EE:FF"
    assert host["broadcast"] == "192.168.1.255"


def test_host_provisioning_values_returns_validation_errors_without_partial_hosts():
    host, error = _build({"name": "bad name"})
    assert host is None
    assert error is not None
    assert "name" in error

    host, error = _build({"name": "Station-A", "labs": ["3"], "validLabIds": ["1", "2"]})
    assert error is None
    assert host is not None
    assert "labs" not in host


def test_host_provisioning_values_derives_coherent_paths_from_discovered_heartbeat():
    host, error = _build({
        "name": "Station-A",
        "heartbeatPath": r"C:\Lab Station\labstation\data\telemetry\heartbeat.json",
        "eventsPath": r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
    })

    assert error is None
    assert host["labstation_exe"] == r"C:\Lab Station\LabStation.exe"
    assert host["local_mode_flag_path"] == r"C:\Lab Station\labstation\data\local-mode.flag"
    assert host["heartbeat_path"] == r"C:\Lab Station\labstation\data\telemetry\heartbeat.json"
    assert host["events_path"] == r"C:\Lab Station\labstation\data\telemetry\session-guard-events.jsonl"
