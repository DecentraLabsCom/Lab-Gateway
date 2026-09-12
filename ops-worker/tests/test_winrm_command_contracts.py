from types import SimpleNamespace

import pytest

import worker


def test_run_labstation_command_contract_preserves_dependencies_payload_and_result(monkeypatch):
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "labstation_exe": r"C:\LabStation\LabStation.exe",
    }
    calls = {}
    session = object()
    result = SimpleNamespace(status_code=7, std_out=b"ok\n", std_err=b"failed\n")
    clock_values = iter((10.0, 10.5))

    def credentials(*args):
        calls["credentials"] = args
        return "user", "password"

    def policy(*args):
        calls["policy"] = args
        return True, 5986, "ntlm"

    def create_session(*args, **kwargs):
        calls["create_session"] = (args, kwargs)
        return session

    def run_method(*args):
        calls["run_method"] = args
        return result

    monkeypatch.setattr(worker, "_winrm_credentials", credentials)
    monkeypatch.setattr(worker, "_winrm_connection_policy", policy)
    monkeypatch.setattr(worker, "create_winrm_session", create_session)
    monkeypatch.setattr(worker, "run_winrm_method", run_method)
    monkeypatch.setattr(worker.time, "time", lambda: next(clock_values))

    response = worker.run_labstation_command(
        host,
        "status-json",
        ["--json"],
        None,
        None,
        "ntlm",
        True,
        5986,
    )

    assert calls["credentials"] == (host, None, None)
    assert calls["policy"] == (host, True, 5986, "ntlm")
    assert calls["create_session"] == (
        (host, "user", "password", "ntlm", 5986),
        {
            "read_timeout_sec": worker.WINRM_READ_TIMEOUT,
            "operation_timeout_sec": worker.WINRM_OPERATION_TIMEOUT,
        },
    )
    assert calls["run_method"] == (
        session,
        "run_cmd",
        r"C:\LabStation\LabStation.exe",
        ["status-json", "--json"],
    )
    assert response == {
        "exit_code": 7,
        "stdout": "ok\n",
        "stderr": "failed\n",
        "duration_ms": 500,
    }


def _patch_remote_command_dependencies(monkeypatch, *, result):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = {}
    session = object()

    def credentials(*args):
        calls["credentials"] = args
        return "user", "password"

    def policy(*args):
        calls["policy"] = args
        return True, 5986, "ntlm"

    def create_session(*args, **kwargs):
        calls["create_session"] = (args, kwargs)
        return session

    def run_method(*args):
        calls["run_method"] = args
        return result

    monkeypatch.setattr(worker, "_winrm_credentials", credentials)
    monkeypatch.setattr(worker, "_winrm_connection_policy", policy)
    monkeypatch.setattr(worker, "create_winrm_session", create_session)
    monkeypatch.setattr(worker, "run_winrm_method", run_method)
    return host, calls, session


def test_run_remote_powershell_contract_preserves_script_and_success_result(monkeypatch):
    result = SimpleNamespace(status_code=0, std_out=b"ok\n", std_err=b"")
    host, calls, session = _patch_remote_command_dependencies(monkeypatch, result=result)

    response = worker.run_remote_powershell(
        host, "Write-Output ok", None, None, "ntlm", True, 5986
    )

    assert calls["credentials"] == (host, None, None)
    assert calls["policy"] == (host, True, 5986, "ntlm")
    assert calls["create_session"] == (
        (host, "user", "password", "ntlm", 5986),
        {
            "read_timeout_sec": worker.WINRM_READ_TIMEOUT,
            "operation_timeout_sec": worker.WINRM_OPERATION_TIMEOUT,
        },
    )
    assert calls["run_method"] == (session, "run_ps", "Write-Output ok")
    assert response == "ok\n"


def test_read_remote_file_contract_preserves_builder_and_success_result(monkeypatch):
    result = SimpleNamespace(status_code=0, std_out=b"contents\n", std_err=b"")
    host, calls, session = _patch_remote_command_dependencies(monkeypatch, result=result)

    def build_read(path):
        calls["builder"] = path
        return "Get-Content"

    monkeypatch.setattr(worker, "_build_read_remote_file_command_impl", build_read)

    response = worker.read_remote_file(host, r"C:\Lab\heartbeat.json", None, None, "ntlm", True, 5986)

    assert calls["builder"] == r"C:\Lab\heartbeat.json"
    assert calls["credentials"] == (host, None, None)
    assert calls["policy"] == (host, True, 5986, "ntlm")
    assert calls["create_session"][0] == (host, "user", "password", "ntlm", 5986)
    assert calls["run_method"] == (session, "run_ps", "Get-Content")
    assert response == "contents\n"


def test_write_remote_file_contract_preserves_builder_and_success_result(monkeypatch):
    result = SimpleNamespace(status_code=0, std_out=b"", std_err=b"")
    host, calls, session = _patch_remote_command_dependencies(monkeypatch, result=result)

    def build_write(path, contents):
        calls["builder"] = (path, contents)
        return "Set-Content"

    monkeypatch.setattr(worker, "_build_write_remote_file_command_impl", build_write)

    response = worker.write_remote_file(
        host, r"C:\Lab\state.txt", "1", None, None, "ntlm", True, 5986
    )

    assert calls["builder"] == (r"C:\Lab\state.txt", "1")
    assert calls["credentials"] == (host, None, None)
    assert calls["policy"] == (host, True, 5986, "ntlm")
    assert calls["create_session"][0] == (host, "user", "password", "ntlm", 5986)
    assert calls["run_method"] == (session, "run_ps", "Set-Content")
    assert response is None


def test_remove_remote_file_contract_preserves_builder_and_success_result(monkeypatch):
    result = SimpleNamespace(status_code=0, std_out=b"", std_err=b"")
    host, calls, session = _patch_remote_command_dependencies(monkeypatch, result=result)

    def build_remove(path):
        calls["builder"] = path
        return "Remove-Item"

    monkeypatch.setattr(worker, "_build_remove_remote_file_command_impl", build_remove)

    response = worker.remove_remote_file(
        host, r"C:\Lab\state.txt", None, None, "ntlm", True, 5986
    )

    assert calls["builder"] == r"C:\Lab\state.txt"
    assert calls["credentials"] == (host, None, None)
    assert calls["policy"] == (host, True, 5986, "ntlm")
    assert calls["create_session"][0] == (host, "user", "password", "ntlm", 5986)
    assert calls["run_method"] == (session, "run_ps", "Remove-Item")
    assert response is None


@pytest.mark.parametrize(
    ("operation", "expected_message"),
    [
        ("powershell", "WinRM PowerShell failed (5): boom\n"),
        ("read", "WinRM read failed (5): boom\n"),
        ("write", "WinRM write failed (5): boom\n"),
        ("remove", "WinRM remove failed (5): boom\n"),
    ],
)
def test_remote_file_contract_preserves_failure_messages(
    monkeypatch, operation, expected_message
):
    result = SimpleNamespace(status_code=5, std_out=b"", std_err=b"boom\n")
    host, _, _ = _patch_remote_command_dependencies(monkeypatch, result=result)

    calls = {
        "powershell": lambda: worker.run_remote_powershell(
            host, "Write-Output ok", None, None, "ntlm", True, 5986
        ),
        "read": lambda: worker.read_remote_file(
            host, r"C:\Lab\state.txt", None, None, "ntlm", True, 5986
        ),
        "write": lambda: worker.write_remote_file(
            host, r"C:\Lab\state.txt", "1", None, None, "ntlm", True, 5986
        ),
        "remove": lambda: worker.remove_remote_file(
            host, r"C:\Lab\state.txt", None, None, "ntlm", True, 5986
        ),
    }

    with pytest.raises(RuntimeError) as exc_info:
        calls[operation]()

    assert str(exc_info.value) == expected_message
