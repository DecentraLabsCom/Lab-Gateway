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


def test_catalog_bool_contract_accepts_supported_values_and_rejects_unknown_text():
    assert host_catalog.catalog_bool(None) is True
    assert host_catalog.catalog_bool("") is True
    assert host_catalog.catalog_bool("true") is True
    assert host_catalog.catalog_bool("1") is True
    assert host_catalog.catalog_bool("off") is False
    assert host_catalog.catalog_bool(False) is False

    with pytest.raises(ValueError, match="winrm_use_ssl must be a boolean"):
        host_catalog.catalog_bool("maybe")


def test_resolve_addresses_contract_preserves_literal_and_dns_resolution():
    assert host_catalog.resolve_addresses(
        "192.168.1.50",
        ip_address=ipaddress.ip_address,
        getaddrinfo=__import__("socket").getaddrinfo,
    ) == [ipaddress.ip_address("192.168.1.50")]

    ip_calls = []

    def fake_ip_address(value):
        if not ip_calls:
            ip_calls.append(value)
            raise ValueError("dns")
        return ipaddress.ip_address(value)

    result = host_catalog.resolve_addresses(
        "station.local",
        ip_address=fake_ip_address,
        getaddrinfo=lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("192.168.1.50", 0)),
            (2, 1, 6, "", ("192.168.1.51", 0)),
        ],
    )

    assert set(result) == {
        ipaddress.ip_address("192.168.1.50"),
        ipaddress.ip_address("192.168.1.51"),
    }


def test_resolve_addresses_contract_fails_closed_for_unresolvable_names():
    with pytest.raises(ValueError, match="cannot be resolved"):
        host_catalog.resolve_addresses(
            "station.local",
            ip_address=lambda _value: (_ for _ in ()).throw(ValueError("dns")),
            getaddrinfo=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        )

    with pytest.raises(ValueError, match="cannot be resolved"):
        host_catalog.resolve_addresses(
            "station.local",
            ip_address=lambda _value: (_ for _ in ()).throw(ValueError("dns")),
            getaddrinfo=lambda *_args, **_kwargs: [],
        )
