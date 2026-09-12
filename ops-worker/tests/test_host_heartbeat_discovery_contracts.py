import json

import worker


def test_discover_heartbeat_hint_contract_preserves_missing_input_and_credentials(
    monkeypatch,
):
    calls = []

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("heartbeat discovery must stop before remote access")

    monkeypatch.setattr(worker, "winrm_credentials_configured", fail_if_called)
    monkeypatch.setattr(worker, "build_heartbeat_path_candidates", fail_if_called)
    monkeypatch.setattr(worker, "read_remote_file", fail_if_called)

    assert worker.discover_heartbeat_hint("") == {
        "checked": False,
        "detected": False,
        "status": "missing-hostname",
    }

    monkeypatch.setattr(
        worker,
        "winrm_credentials_configured",
        lambda hostname: calls.append(("credentials", hostname)) or False,
    )
    assert worker.discover_heartbeat_hint("lab-candidate") == {
        "checked": False,
        "detected": False,
        "status": "missing-winrm-credentials",
    }
    assert calls == [("credentials", "lab-candidate")]


def test_discover_heartbeat_hint_contract_preserves_first_valid_path_and_mac(
    monkeypatch,
):
    calls = []
    heartbeat = {"status": {"wake": {"nicPower": []}}}
    mac_hint = {"mac": "00:11:22:33:44:55", "source": "heartbeat"}
    failure = RuntimeError("missing")

    class FakeLogger:
        def debug(self, *args):
            calls.append(("debug", *args))

    def credentials(hostname):
        calls.append(("credentials", hostname))
        return True

    def candidates(host):
        calls.append(("candidates", host.copy()))
        return [r"C:\Missing\heartbeat.json", r"D:\Lab\heartbeat.json"]

    def read_file(host, path, *args):
        calls.append(("read", host.copy(), path, args))
        if path.startswith("C:"):
            raise failure
        return json.dumps(heartbeat)

    def suggest(received_heartbeat):
        calls.append(("suggest", received_heartbeat))
        return mac_hint

    monkeypatch.setattr(worker, "WINRM_PORT", 55986)
    monkeypatch.setattr(worker, "winrm_credentials_configured", credentials)
    monkeypatch.setattr(worker, "build_heartbeat_path_candidates", candidates)
    monkeypatch.setattr(worker, "read_remote_file", read_file)
    monkeypatch.setattr(worker, "suggest_mac_from_heartbeat", suggest)
    monkeypatch.setattr(worker, "logging", FakeLogger())

    result = worker.discover_heartbeat_hint("lab-candidate")

    expected_host = {
        "name": "lab-candidate",
        "address": "lab-candidate",
        "credential_ref": "lab-candidate",
        "winrm_transport": "ntlm",
        "winrm_use_ssl": True,
        "winrm_port": 55986,
    }
    assert result == {
        "checked": True,
        "detected": True,
        "path": r"D:\Lab\heartbeat.json",
        "suggestedMac": mac_hint,
    }
    assert calls == [
        ("credentials", "lab-candidate"),
        ("candidates", expected_host),
        ("read", expected_host, r"C:\Missing\heartbeat.json", (None, None, None, None, None)),
        ("debug", "Unable to read heartbeat candidate %s: %s", r"C:\Missing\heartbeat.json", failure),
        ("read", expected_host, r"D:\Lab\heartbeat.json", (None, None, None, None, None)),
        ("suggest", heartbeat),
    ]


def test_discover_heartbeat_hint_contract_preserves_read_failure_shape(monkeypatch):
    monkeypatch.setattr(worker, "winrm_credentials_configured", lambda _hostname: True)
    monkeypatch.setattr(
        worker,
        "build_heartbeat_path_candidates",
        lambda _host: [r"C:\Missing\one.json", r"C:\Missing\two.json"],
    )
    monkeypatch.setattr(
        worker,
        "read_remote_file",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("missing")),
    )

    assert worker.discover_heartbeat_hint("lab-candidate") == {
        "checked": True,
        "detected": False,
        "status": "read-failed",
        "errors": [
            {"path": r"C:\Missing\one.json", "error": "Remote heartbeat read failed"},
            {"path": r"C:\Missing\two.json", "error": "Remote heartbeat read failed"},
        ],
    }
