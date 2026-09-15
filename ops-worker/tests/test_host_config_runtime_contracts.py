from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from guacamole_dsn import build_guacamole_dsn
from host_config_runtime import HostConfigRuntime, create_host_config_runtime
from host_config_context import HostConfigContext
from ops_dsn import build_ops_dsn


def _context(**overrides):
    calls = overrides.pop("calls", [])
    state = {
        "config_path": "base.json",
        "dynamic_path": "dynamic.json",
        "hosts": SimpleNamespace(get=lambda _name: None, get_by_lab=lambda _lab: None),
    }

    def read_config(path, missing_ok=True):
        calls.append(("read", path, missing_ok))
        return {"hosts": []}

    def load_config(config_path, dynamic_path, **kwargs):
        base = kwargs["read_config"](config_path, missing_ok=False)
        dynamic = kwargs["read_config"](dynamic_path, missing_ok=True)
        merged = kwargs["merge_configs"](base, dynamic)
        kwargs["validate_config"](merged)
        return kwargs["resolve_secret_refs"](merged)

    values = {
        "read_hosts_config_impl": read_config,
        "merge_host_configs_impl": lambda base, dynamic: calls.append(
            ("merge", base, dynamic)
        ) or {"hosts": [{"name": "merged"}]},
        "resolve_host_secret_refs_impl": lambda config, **kwargs: calls.append(
            ("resolve", config, kwargs)
        ) or {"hosts": [{"name": "resolved"}]},
        "get_credential_ref_for_host": lambda: lambda _host: "credential",
        "get_credentials_configured": lambda: lambda _ref: True,
        "get_logger": lambda: SimpleNamespace(
            warning=lambda *args: calls.append(("warning", args))
        ),
        "catalog_bool_impl": lambda value: value,
        "resolve_addresses_impl": lambda address, **kwargs: [address],
        "get_ip_address": lambda: lambda value: value,
        "get_getaddrinfo": lambda: lambda *args, **kwargs: [],
        "validate_winrm_catalog_impl": lambda config, **kwargs: calls.append(
            ("validate", config, kwargs)
        ),
        "get_management_cidrs": lambda: ["10.0.0.0/8"],
        "get_winrm_port": lambda: 5986,
        "get_trust_ref_pattern": lambda: "trust-pattern",
        "get_catalog_bool": lambda: lambda value: value,
        "get_resolved_addresses": lambda: lambda address: [address],
        "load_host_config_impl": load_config,
        "get_config_path": lambda: state["config_path"],
        "get_dynamic_config_path": lambda: state["dynamic_path"],
        "get_read_hosts_config": lambda: read_config,
        "get_merge_host_configs": lambda: lambda base, dynamic: calls.append(
            ("merge", base, dynamic)
        ) or {"hosts": [{"name": "merged"}]},
        "get_validate_winrm_catalog": lambda: lambda config: calls.append(
            ("validate", config, {})
        ),
        "get_resolve_host_secret_refs": lambda: lambda config: calls.append(
            ("resolve", config, {})
        ) or {"hosts": [{"name": "resolved"}]},
        "build_ops_dsn_impl": build_ops_dsn,
        "get_mysql_dsn": lambda: None,
        "get_ops_mysql_user": lambda: "ops",
        "get_ops_mysql_password": lambda: "secret",
        "get_ops_mysql_database": lambda: "ops_db",
        "get_mysql_hostname": lambda: "mysql",
        "get_mysql_port": lambda: 3306,
        "get_url_create": lambda: lambda *args, **kwargs: SimpleNamespace(
            render_as_string=lambda hide_password: "ops-rendered"
        ),
        "build_guacamole_dsn_impl": build_guacamole_dsn,
        "get_guacamole_dsn": lambda: None,
        "get_guacamole_user": lambda: "guac",
        "get_guacamole_password": lambda: "secret",
        "get_guacamole_database": lambda: "guac_db",
        "get_parse_url": lambda: lambda value: SimpleNamespace(
            set=lambda **kwargs: "derived-rendered"
        ),
        "get_load_dynamic_config": lambda: lambda: {"hosts": []},
        "get_write_dynamic_config": lambda: lambda _config: None,
        "load_dynamic_config_impl": lambda path, **kwargs: kwargs["read_config"](
            path,
            missing_ok=True,
        ),
        "write_dynamic_config_impl": lambda *args, **kwargs: calls.append(
            ("write-dynamic", args, kwargs)
        ),
        "get_path_dirname": lambda: lambda path: "dir",
        "get_make_dirs": lambda: lambda *args, **kwargs: None,
        "get_open_file": lambda: open,
        "get_dump_json": lambda: lambda *args, **kwargs: None,
        "get_replace_file": lambda: lambda *args: None,
        "upsert_dynamic_host_impl": lambda *args, **kwargs: calls.append(
            ("upsert", args, kwargs)
        ),
        "get_normalize_match_key": lambda: lambda value: str(value).lower(),
        "get_sanitize_host_name": lambda: lambda value, fallback: (value or fallback, None),
        "get_normalize_mac": lambda: lambda value: value,
        "get_host_get": lambda: state["hosts"].get,
        "update_dynamic_host_impl": lambda *args, **kwargs: calls.append(
            ("update", args, kwargs)
        ) or ({"name": args[0]}, None),
    }
    values.update(overrides)
    return HostConfigContext(**values), state, calls


def test_host_config_runtime_forwards_catalog_lifecycle_and_dsn_inputs():
    context, _state, calls = _context()
    runtime = create_host_config_runtime(context)

    assert isinstance(runtime, HostConfigRuntime)
    assert runtime.load_config() == {"hosts": [{"name": "resolved"}]}
    assert runtime.build_ops_dsn() == "ops-rendered"
    assert runtime.build_guacamole_dsn() == "ops-rendered"
    assert calls[:5] == [
        ("read", "base.json", False),
        ("read", "dynamic.json", True),
        ("merge", {"hosts": []}, {"hosts": []}),
        ("validate", {"hosts": [{"name": "merged"}]}, calls[3][2]),
        ("resolve", {"hosts": [{"name": "merged"}]}, calls[4][2]),
    ]


def test_host_config_runtime_resolves_mutable_paths_and_aliases_at_call_time():
    context, state, calls = _context(
        load_dynamic_config_impl=lambda path, **kwargs: kwargs["read_config"](
            path,
            missing_ok=True,
        ),
        get_read_hosts_config=lambda: lambda path, missing_ok=True: calls.append(
            ("alias", path, missing_ok)
        ) or {"hosts": []},
    )
    runtime = create_host_config_runtime(context)
    state["dynamic_path"] = "second.json"

    assert runtime.load_dynamic_config() == {"hosts": []}
    assert calls == [("alias", "second.json", True)]


def test_host_config_context_is_immutable():
    context, _state, _calls = _context()

    with pytest.raises(FrozenInstanceError):
        context.get_logger = lambda: SimpleNamespace()
