import ipaddress
import re

import pytest

import host_catalog


def _validate(config, *, cidrs=("192.168.1.0/24",), port=5986):
    return host_catalog.validate_winrm_catalog(
        config,
        management_cidrs=cidrs,
        winrm_port=port,
        catalog_bool=lambda value: value is not False,
        resolve_addresses=lambda _address: [ipaddress.ip_address("192.168.1.50")],
        trust_ref_pattern=re.compile(r"^[A-Za-z0-9._-]+$"),
    )


def _host(**overrides):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    host.update(overrides)
    return host


def test_host_catalog_accepts_secure_hosts_inside_management_network():
    assert _validate({"hosts": [_host()]}) is None


def test_host_catalog_rejects_missing_policy_and_invalid_networks():
    missing_port = _host()
    missing_port.pop("winrm_port")
    with pytest.raises(ValueError, match="declare winrm_use_ssl and winrm_port"):
        _validate({"hosts": [missing_port]})

    with pytest.raises(ValueError, match="invalid network"):
        _validate({"hosts": [_host()]}, cidrs=("not-a-network",))


def test_host_catalog_rejects_hosts_outside_management_network():
    with pytest.raises(ValueError, match="outside WINRM_MANAGEMENT_CIDRS"):
        _validate(
            {"hosts": [_host()]},
            cidrs=("10.0.0.0/8",),
        )
