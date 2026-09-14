from types import SimpleNamespace

from credential_runtime import CredentialRuntime, create_credential_runtime


def test_credential_runtime_forwards_store_and_reference_dependencies():
    calls = []
    providers = {
        "_FERNET": None,
        "_load_fernet_store_impl": lambda current, **kwargs: calls.append(
            ("fernet", current, kwargs)
        ) or "fernet",
        "_env_or_secret_file": lambda name: f"secret:{name}",
        "Fernet": "fernet-factory",
        "_normalize_credential_ref_impl": lambda value: calls.append(
            ("normalize", value)
        ) or "ref",
        "_credential_ref_for_host_impl": lambda host, **kwargs: calls.append(
            ("host-ref", host, kwargs)
        ) or "host-ref",
        "_read_credentials_store_impl": lambda path: calls.append(("read", path)) or {"ref": {}},
        "OPS_CREDENTIALS_PATH": "credentials.json",
        "_write_credentials_store_impl": lambda path, data: calls.append(
            ("write", path, data)
        ),
        "_save_credentials_store_impl": lambda *args, **kwargs: calls.append(
            ("save", args, kwargs)
        ),
        "_load_credentials_store_impl": lambda *args, **kwargs: calls.append(
            ("load", args, kwargs)
        ) or {"user": "user", "password": "password"},
        "logging": SimpleNamespace(),
        "normalize_credential_ref": lambda value: "ref",
        "credential_ref_for_host": lambda host: "host-ref",
        "_load_fernet": lambda: "fernet",
        "load_winrm_credentials": lambda value: {"user": "user", "password": "password"},
        "read_winrm_credentials_store": lambda: {"ref": {}},
        "write_winrm_credentials_store": lambda data: None,
    }
    runtime = create_credential_runtime(providers)

    assert isinstance(runtime, CredentialRuntime)
    assert runtime.load_fernet() == "fernet"
    assert providers["_FERNET"] == "fernet"
    assert runtime.normalize_credential_ref("Ref") == "ref"
    assert runtime.credential_ref_for_host({"name": "host"}) == "host-ref"
    assert runtime.read_winrm_credentials_store() == {"ref": {}}
    assert runtime.write_winrm_credentials_store({"ref": {}}) is None
    assert runtime.save_winrm_credentials("ref", "user", "password") is None
    assert runtime.load_winrm_credentials("ref") == {"user": "user", "password": "password"}
    assert runtime.winrm_credentials_configured("ref") is True
    assert any(call[0] == "save" for call in calls)


def test_credential_runtime_resolves_mutable_fernet_and_store_callbacks():
    providers = {
        "_FERNET": "first",
        "_load_fernet_store_impl": lambda current, **kwargs: current,
        "_env_or_secret_file": lambda name: "secret",
        "Fernet": "factory",
        "_normalize_credential_ref_impl": lambda value: value,
        "_credential_ref_for_host_impl": lambda host, **kwargs: "first",
        "_read_credentials_store_impl": lambda path: {},
        "OPS_CREDENTIALS_PATH": "first.json",
        "_write_credentials_store_impl": lambda path, data: None,
        "_save_credentials_store_impl": lambda *args, **kwargs: None,
        "_load_credentials_store_impl": lambda *args, **kwargs: None,
        "logging": SimpleNamespace(),
        "normalize_credential_ref": lambda value: value,
        "credential_ref_for_host": lambda host: "first",
        "_load_fernet": lambda: providers["_FERNET"],
        "load_winrm_credentials": lambda value: None,
        "read_winrm_credentials_store": lambda: {},
        "write_winrm_credentials_store": lambda data: None,
    }
    runtime = create_credential_runtime(providers)

    providers["OPS_CREDENTIALS_PATH"] = "second.json"
    assert runtime.read_winrm_credentials_store() == {}
    assert runtime._providers["OPS_CREDENTIALS_PATH"] == "second.json"


def test_credential_runtime_forwards_fernet_health_callback():
    calls = []
    providers = {
        "_fernet_key_is_usable_impl": lambda **kwargs: calls.append(kwargs) or True,
        "_load_fernet": lambda: "fernet",
        "logging": "logger",
    }
    runtime = create_credential_runtime(providers)

    assert runtime.fernet_key_is_usable() is True
    assert calls == [{"load_fernet": providers["_load_fernet"], "logger": "logger"}]
