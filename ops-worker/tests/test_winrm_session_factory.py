import winrm_session_factory


def test_session_factory_builds_validated_endpoint_and_options_from_explicit_dependencies():
    calls = {}
    host = {"address": "192.168.1.50"}

    def load_trust(received_host):
        calls["trust_host"] = received_host
        return "/data/winrm/server.pem", {"status": "ready"}

    def session_factory(endpoint, **kwargs):
        calls["endpoint"] = endpoint
        calls["kwargs"] = kwargs
        return "session"

    result = winrm_session_factory.create_winrm_session(
        host,
        "user",
        "password",
        "ntlm",
        5986,
        read_timeout_sec=30,
        operation_timeout_sec=20,
        load_trust=load_trust,
        session_factory=session_factory,
    )

    assert result == "session"
    assert calls["trust_host"] is host
    assert calls["endpoint"] == "https://192.168.1.50:5986/wsman"
    assert calls["kwargs"] == {
        "auth": ("user", "password"),
        "transport": "ntlm",
        "ca_trust_path": "/data/winrm/server.pem",
        "server_cert_validation": "validate",
        "read_timeout_sec": 30,
        "operation_timeout_sec": 20,
    }


def test_session_factory_omits_optional_timeouts_when_not_configured():
    calls = {}

    def load_trust(_host):
        return "/data/winrm/server.pem", {}

    def session_factory(endpoint, **kwargs):
        calls.update(endpoint=endpoint, kwargs=kwargs)
        return object()

    winrm_session_factory.create_winrm_session(
        {"address": "station.example"},
        "user",
        "password",
        "kerberos",
        5986,
        load_trust=load_trust,
        session_factory=session_factory,
    )

    assert calls["kwargs"] == {
        "auth": ("user", "password"),
        "transport": "kerberos",
        "ca_trust_path": "/data/winrm/server.pem",
        "server_cert_validation": "validate",
    }
