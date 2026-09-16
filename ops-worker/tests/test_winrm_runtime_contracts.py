from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Callable, Dict, Tuple

import pytest

from winrm_context import WinRMContext
from winrm_runtime import WinRMRuntime, create_winrm_runtime


def _context(**overrides):
    values = {
        "get_winrm_port": lambda: 5986,
        "get_allowed_transports": lambda: {"ntlm"},
        "coerce_bool": lambda value: value,
        "get_credential_ref_for_host": lambda host: "ref",
        "get_load_credentials": lambda ref: {"user": "user", "password": "password"},
        "get_credentials_required_message": lambda: "required",
        "get_load_trust": lambda host: ("server.pem", {}),
        "get_session_factory": lambda: lambda *args, **kwargs: object(),
        "get_ssl_error_type": lambda: RuntimeError,
        "get_trust_error_type": lambda: ValueError,
        "tls_error_code": "WINRM_TLS_FAILED",
        "tls_error_message": "TLS failed",
        "get_default_executable": lambda: "LabStation.exe",
        "get_read_timeout_sec": lambda: 30,
        "get_operation_timeout_sec": lambda: 20,
        "get_logger": lambda: SimpleNamespace(info=lambda *args: None),
        "clock": lambda: 100.0,
        "get_resolve_credentials": lambda: lambda *args: ("user", "password"),
        "get_resolve_policy": lambda: lambda *args: (True, 5986, "ntlm"),
        "get_create_session": lambda: lambda *args, **kwargs: object(),
        "get_run_method": lambda: lambda *args: object(),
        "get_build_labstation_command": lambda: lambda *args: ("command", []),
        "get_build_read_remote_file_command": lambda: lambda path: "read-command",
        "get_build_write_remote_file_command": lambda: lambda path, contents: "write-command",
        "get_build_remove_remote_file_command": lambda: lambda path: "remove-command",
    }
    values.update(overrides)
    return WinRMContext(**values)


def test_winrm_runtime_uses_explicit_context_dependencies():
    calls = []
    result = SimpleNamespace(status_code=7, std_out=b"ok\n", std_err=b"failed\n")
    clock_values = iter((10.0, 10.5))
    context = _context(
        get_resolve_credentials=lambda: lambda *args: calls.append(
            ("credentials", args)
        ) or ("user", "password"),
        get_resolve_policy=lambda: lambda *args: calls.append(("policy", args))
        or (True, 5986, "ntlm"),
        get_create_session=lambda: lambda *args, **kwargs: calls.append(
            ("session", args, kwargs)
        ) or object(),
        get_run_method=lambda: lambda *args: calls.append(("method", args)) or result,
        get_build_labstation_command=lambda: lambda *args: calls.append(
            ("builder", args)
        ) or ("LabStation.exe", ["status-json"]),
        clock=lambda: next(clock_values),
    )
    runtime = create_winrm_runtime(context)

    assert isinstance(runtime, WinRMRuntime)
    assert runtime.winrm_connection_policy(
        {"winrm_use_ssl": True, "winrm_port": 5986}, None, None, None
    ) == (True, 5986, "ntlm")
    assert runtime.winrm_credentials({}, None, None) == ("user", "password")
    assert runtime.run_labstation_command(
        {"address": "192.0.2.10"}, "status-json", [], None, None, None, None, None
    ) == {
        "exit_code": 7,
        "stdout": "ok\n",
        "stderr": "failed\n",
        "duration_ms": 500,
    }
    assert [call[0] for call in calls] == ["credentials", "policy", "session", "builder", "method"]


def test_winrm_context_is_immutable_and_preserves_live_patch_points():
    callbacks: Dict[str, Callable[..., Tuple[bool, int, str]]] = {
        "policy": lambda *args: (True, 6000, "ntlm")
    }
    context = _context(get_resolve_policy=lambda: callbacks["policy"])
    runtime = create_winrm_runtime(context)

    assert runtime.winrm_endpoint({"address": "192.0.2.10"}, None, None) == (
        "https://192.0.2.10:6000/wsman"
    )
    callbacks["policy"] = lambda *args: (True, 6443, "ntlm")
    assert runtime.winrm_endpoint({"address": "192.0.2.10"}, None, None) == (
        "https://192.0.2.10:6443/wsman"
    )

    with pytest.raises(FrozenInstanceError):
        setattr(context, "tls_error_code", "changed")
