import pytest

import winrm_session_policy
import worker


def _host(**overrides):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 5986,
    }
    host.update(overrides)
    return host


def _resolve(host, use_ssl=None, port=None, transport=None, *, winrm_port=5986, allowed=None):
    return winrm_session_policy.resolve_winrm_connection_policy(
        host,
        use_ssl,
        port,
        transport,
        winrm_port=winrm_port,
        allowed_transports=allowed or {"ntlm", "kerberos", "credssp"},
        coerce_bool=worker._coerce_bool,
    )


def test_connection_policy_uses_declared_secure_defaults():
    assert _resolve(_host()) == (True, 5986, "ntlm")


def test_connection_policy_rejects_plaintext_and_noncanonical_ports():
    with pytest.raises(ValueError, match="HTTPS"):
        _resolve(_host(winrm_use_ssl=False))

    with pytest.raises(ValueError, match="port"):
        _resolve(_host(), port=5985)


def test_connection_policy_rejects_transport_override_and_unknown_transport():
    with pytest.raises(ValueError, match="transport"):
        _resolve(_host(), transport="kerberos")

    with pytest.raises(ValueError, match="not allowed"):
        _resolve(_host(winrm_transport="basic"), allowed={"ntlm"})


def test_connection_policy_reports_invalid_host_and_request_values():
    with pytest.raises(ValueError, match="declare winrm_use_ssl and winrm_port"):
        _resolve({"winrm_use_ssl": True})

    with pytest.raises(ValueError, match="host winrm_port is invalid"):
        _resolve(_host(winrm_port="5986.5"))

    with pytest.raises(ValueError, match="request port is invalid"):
        _resolve(_host(), port="5986.5")


def test_worker_facade_keeps_dynamic_gateway_policy_configuration(monkeypatch):
    monkeypatch.setattr(worker, "WINRM_PORT", 6000)
    host = _host(winrm_port=6000)

    assert worker._winrm_connection_policy(host, None, None, None) == (
        True,
        6000,
        "ntlm",
    )
