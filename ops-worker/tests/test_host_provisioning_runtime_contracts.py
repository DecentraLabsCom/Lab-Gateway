import re
from dataclasses import FrozenInstanceError
from typing import Any, Callable, Dict

import pytest

from host_provisioning_context import HostProvisioningContext
from host_provisioning_runtime import HostProvisioningRuntime, create_host_provisioning_runtime


def _context(**overrides):
    values = {
        "get_name_pattern": lambda: re.compile(r"[A-Za-z0-9._-]+"),
        "normalize_mac": lambda value: "AA:BB:CC:DD:EE:FF",
        "normalize_trust_ref": lambda value: "station-01",
        "get_sanitize_host_name": lambda value, fallback: ("station-01", None),
        "default_heartbeat_path": r"C:\LabStation\heartbeat.json",
        "default_events_path": r"C:\LabStation\events.jsonl",
    }
    values.update(overrides)
    return HostProvisioningContext(**values)


def test_host_provisioning_runtime_uses_explicit_context_dependencies():
    calls = []
    context = _context(
        get_sanitize_host_name=lambda value, fallback: calls.append(
            ("name", value, fallback)
        ) or ("station-01", None),
    )
    runtime = create_host_provisioning_runtime(context)

    assert isinstance(runtime, HostProvisioningRuntime)
    assert runtime.sanitize_host_name("station-01", "fallback") == ("station-01", None)
    assert runtime.build_provisioned_host(
        {"name": "station-01", "mac": "001122334455"}, {"hostname": "station-01"}
    ) == (
        {
            "name": "station-01",
            "address": "station-01",
            "credential_ref": "station-01",
            "winrm_trust_ref": "station-01",
            "winrm_transport": "ntlm",
            "winrm_use_ssl": True,
            "winrm_port": 5986,
            "heartbeat_path": r"C:\LabStation\heartbeat.json",
            "events_path": r"C:\LabStation\events.jsonl",
            "mac": "AA:BB:CC:DD:EE:FF",
        },
        None,
    )
    assert ("name", "station-01", "station-01") in calls


def test_host_provisioning_context_is_immutable_and_can_wrap_live_callbacks():
    callbacks: Dict[str, Callable[[Any], str]] = {
        "trust_ref": lambda value: "first"
    }
    context = _context(normalize_trust_ref=lambda value: callbacks["trust_ref"](value))
    runtime = create_host_provisioning_runtime(context)

    first_host, first_error = runtime.build_provisioned_host({}, {"hostname": "station-01"})
    assert first_error is None
    assert first_host is not None
    assert first_host["winrm_trust_ref"] == "first"
    callbacks["trust_ref"] = lambda value: "second"
    second_host, second_error = runtime.build_provisioned_host({}, {"hostname": "station-01"})
    assert second_error is None
    assert second_host is not None
    assert second_host["winrm_trust_ref"] == "second"

    with pytest.raises(FrozenInstanceError):
        setattr(context, "default_heartbeat_path", r"C:\other.json")
