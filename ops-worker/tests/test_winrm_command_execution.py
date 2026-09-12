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


def test_run_winrm_method_maps_tls_failures_to_the_stable_trust_error():
    with pytest.raises(FakeTrustError, match="WinRM TLS validation failed") as exc_info:
        _run(TlsFailingSession(), "run_ps", "Write-Output ok")

    assert exc_info.value.code == "WINRM_TLS_FAILED"
