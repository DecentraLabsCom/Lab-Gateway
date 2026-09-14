from types import SimpleNamespace

from winrm_runtime import WinRMRuntime, create_winrm_runtime


def test_winrm_runtime_resolves_live_policy_and_command_callbacks():
    calls = []
    providers = {
        "_resolve_winrm_connection_policy_impl": lambda *args, **kwargs: calls.append(
            ("policy", args, kwargs)
        ) or (True, 5986, "ntlm"),
        "WINRM_PORT": 5986,
        "WINRM_ALLOWED_TRANSPORTS": {"ntlm"},
        "_coerce_bool": lambda value: value,
        "_resolve_winrm_credentials_impl": lambda *args, **kwargs: calls.append(
            ("credentials", args, kwargs)
        ) or ("user", "password"),
        "credential_ref_for_host": lambda host: "ref",
        "load_winrm_credentials": lambda ref: {"user": "user", "password": "password"},
        "WINRM_CREDENTIALS_REQUIRED_MESSAGE": "required",
        "_run_labstation_command_impl": lambda *args, **kwargs: calls.append(
            ("command", args, kwargs)
        ) or {"exit_code": 0},
        "_winrm_credentials": lambda *args: ("user", "password"),
        "_winrm_connection_policy": lambda *args: (True, 5986, "ntlm"),
        "create_winrm_session": lambda *args, **kwargs: object(),
        "run_winrm_method": lambda *args: object(),
        "_build_labstation_command_impl": lambda *args: "command",
        "DEFAULT_LABSTATION_EXE": "LabStation.exe",
        "WINRM_READ_TIMEOUT": 30,
        "WINRM_OPERATION_TIMEOUT": 20,
        "logging": SimpleNamespace(),
        "time": SimpleNamespace(time=lambda: 100),
    }
    runtime = create_winrm_runtime(providers)

    assert isinstance(runtime, WinRMRuntime)
    assert runtime.winrm_connection_policy({}, None, None, None) == (True, 5986, "ntlm")
    assert runtime.winrm_credentials({}, None, None) == ("user", "password")
    assert runtime.run_labstation_command({}, "status", [], None, None, None, None, None) == {
        "exit_code": 0
    }
    assert [call[0] for call in calls] == ["policy", "credentials", "command"]
