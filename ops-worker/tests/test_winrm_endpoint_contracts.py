import worker


def test_winrm_endpoint_contract_uses_current_policy_and_https_shape(monkeypatch):
    host = {"address": "192.168.1.50"}
    calls = []

    def resolve_policy(received_host, use_ssl, port, transport):
        calls.append((received_host, use_ssl, port, transport))
        return True, 6000, "ntlm"

    monkeypatch.setattr(worker, "_winrm_connection_policy", resolve_policy)

    assert worker.winrm_endpoint(host, False, 5985) == "https://192.168.1.50:6000/wsman"
    assert calls == [(host, False, 5985, None)]


def test_winrm_endpoint_contract_propagates_policy_validation_errors(monkeypatch):
    failure = ValueError("WinRM HTTPS is required by gateway policy")
    monkeypatch.setattr(
        worker,
        "_winrm_connection_policy",
        lambda *_args: (_ for _ in ()).throw(failure),
    )

    try:
        worker.winrm_endpoint({"address": "lab-01"}, None, None)
    except ValueError as exc:
        assert exc is failure
    else:
        raise AssertionError("winrm_endpoint must propagate policy errors")
