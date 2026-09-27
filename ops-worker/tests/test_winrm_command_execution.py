import pytest

import winrm_command_execution


class FakeTlsError(Exception):
    pass


class FakeTrustError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Session:
    def run_ps(self, script):
        return {"script": script}


class DirectProtocol:
    def __init__(self):
        self.calls = []

    def open_shell(self):
        self.calls.append(("open_shell",))
        return "shell"

    def run_command(self, shell_id, command, arguments, *, skip_cmd_shell):
        self.calls.append(("run_command", shell_id, command, arguments, skip_cmd_shell))
        return "command"

    def get_command_output(self, shell_id, command_id):
        self.calls.append(("get_command_output", shell_id, command_id))
        return b"ok\n", b"", 0

    def cleanup_command(self, shell_id, command_id):
        self.calls.append(("cleanup_command", shell_id, command_id))

    def close_shell(self, shell_id):
        self.calls.append(("close_shell", shell_id))


class DirectSession:
    def __init__(self):
        self.protocol = DirectProtocol()


class TlsFailingSession:
    def run_ps(self, _script):
        raise FakeTlsError("certificate verify failed")


def _run(session, method_name="run_ps", *args):
    return winrm_command_execution.run_winrm_method(
        session,
        method_name,
        *args,
        ssl_error_type=FakeTlsError,
        trust_error_factory=FakeTrustError,
        tls_error_code="WINRM_TLS_FAILED",
        tls_error_message="WinRM TLS validation failed",
    )


def test_run_winrm_method_forwards_method_and_arguments():
    assert _run(Session(), "run_ps", "Write-Output ok") == {"script": "Write-Output ok"}


def test_run_winrm_method_executes_commands_without_the_cmd_shell():
    session = DirectSession()

    result = _run(
        session,
        "run_cmd_direct",
        r"C:\Lab Station\LabStation.exe",
        ["power", "shutdown"],
    )

    assert result.status_code == 0
    assert result.std_out == b"ok\n"
    assert session.protocol.calls == [
        ("open_shell",),
        (
            "run_command",
            "shell",
            r"C:\Lab Station\LabStation.exe",
            ["power", "shutdown"],
            True,
        ),
        ("get_command_output", "shell", "command"),
        ("cleanup_command", "shell", "command"),
        ("close_shell", "shell"),
    ]


def test_run_winrm_method_maps_tls_failures_to_the_stable_trust_error():
    with pytest.raises(FakeTrustError, match="WinRM TLS validation failed") as exc_info:
        _run(TlsFailingSession(), "run_ps", "Write-Output ok")

    assert exc_info.value.code == "WINRM_TLS_FAILED"
