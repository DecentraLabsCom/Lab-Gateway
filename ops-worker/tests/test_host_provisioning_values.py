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
        normalize_labs_fn=host_provisioning_values.normalize_labs,
        validate_labs_fn=host_provisioning_values.validate_labs_against_candidates,
        normalize_mac_fn=lambda value: value.replace("-", ":").upper() if value == "AA-BB-CC-DD-EE-FF" else "",
        normalize_trust_ref_fn=lambda value: str(value).lower(),
        default_heartbeat_path=r"C:\LabStation\heartbeat.json",
        default_events_path=r"C:\LabStation\events.jsonl",
    )


def test_host_provisioning_values_normalizes_labs_and_builds_secure_defaults():
    assert host_provisioning_values.normalize_labs("1, 2") == ["1", "2"]
    assert host_provisioning_values.validate_labs_against_candidates(["1"], ["1", "2"]) is None

    host, error = _build({"name": "Station-A", "labs": "1,2", "mac": "AA-BB-CC-DD-EE-FF"})

    assert error is None
    assert host["name"] == "Station-A"
    assert host["winrm_use_ssl"] is True
    assert host["winrm_port"] == 5986
    assert host["labs"] == ["1", "2"]
    assert host["mac"] == "AA:BB:CC:DD:EE:FF"


def test_host_provisioning_values_returns_validation_errors_without_partial_hosts():
    host, error = _build({"name": "bad name"})
    assert host is None
    assert "name" in error

    host, error = _build({"name": "Station-A", "labs": ["3"], "validLabIds": ["1", "2"]})
    assert host is None
    assert "not valid candidates" in error
