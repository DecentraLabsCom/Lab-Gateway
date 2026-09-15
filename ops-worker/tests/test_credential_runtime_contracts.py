from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from credential_context import CredentialContext
from credential_runtime import CredentialRuntime, create_credential_runtime


def _context(**overrides):
    cache = {"value": None}
    state = {"path": "credentials.json"}
    calls = overrides.pop("calls", [])
    values = {
        "load_fernet_impl": lambda current, **kwargs: calls.append(
            ("fernet", current, kwargs)
        ) or "fernet",
        "get_cached_fernet": lambda: cache["value"],
        "set_cached_fernet": lambda value: cache.__setitem__("value", value),
        "get_load_fernet": lambda: lambda: cache["value"],
        "get_read_secret": lambda: lambda name: f"secret:{name}",
        "get_fernet_factory": lambda: "fernet-factory",
        "normalize_credential_ref": lambda value: calls.append(
            ("normalize", value)
        ) or "ref",
        "credential_ref_for_host": lambda host, **kwargs: calls.append(
            ("host-ref", host, kwargs)
        ) or "host-ref",
        "read_credentials_store_impl": lambda path: calls.append(
            ("read", path)
        ) or {"credentials": {}},
        "get_credentials_path": lambda: state["path"],
        "write_credentials_store_impl": lambda path, data: calls.append(
            ("write", path, data)
        ),
        "save_credentials_impl": lambda *args, **kwargs: calls.append(
            ("save", args, kwargs)
        ),
        "load_credentials_impl": lambda *args, **kwargs: calls.append(
            ("load", args, kwargs)
        ) or {"user": "user", "password": "password"},
        "fernet_key_is_usable_impl": lambda **kwargs: calls.append(
            ("health", kwargs)
        ) or True,
        "get_logger": lambda: SimpleNamespace(),
    }
    values.update(overrides)
    return CredentialContext(**values), cache, state, calls


def test_credential_runtime_forwards_store_and_reference_dependencies():
    context, cache, _state, calls = _context()
    runtime = create_credential_runtime(context)

    assert isinstance(runtime, CredentialRuntime)
    assert runtime.load_fernet() == "fernet"
    assert cache["value"] == "fernet"
    assert runtime.normalize_credential_ref("Ref") == "ref"
    assert runtime.credential_ref_for_host({"name": "host"}) == "host-ref"
    assert runtime.read_winrm_credentials_store() == {"credentials": {}}
    assert runtime.write_winrm_credentials_store({"credentials": {}}) is None
    assert runtime.save_winrm_credentials("ref", "user", "password") is None
    assert runtime.load_winrm_credentials("ref") == {
        "user": "user",
        "password": "password",
    }
    assert runtime.winrm_credentials_configured("ref") is True
    assert runtime.fernet_key_is_usable() is True
    assert any(call[0] == "save" for call in calls)


def test_credential_runtime_resolves_mutable_cache_and_store_path_at_call_time():
    context, cache, state, _calls = _context(
        load_fernet_impl=lambda current, **kwargs: current,
        read_credentials_store_impl=lambda path: {"path": path},
    )
    cache["value"] = "first"
    runtime = create_credential_runtime(context)

    state["path"] = "second.json"
    assert runtime.load_fernet() == "first"
    assert runtime.read_winrm_credentials_store() == {"path": "second.json"}


def test_credential_context_is_immutable():
    context, _cache, _state, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_logger = lambda: SimpleNamespace()
