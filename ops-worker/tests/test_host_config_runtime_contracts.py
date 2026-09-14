from types import SimpleNamespace

from host_config_runtime import HostConfigRuntime, create_host_config_runtime
from guacamole_dsn import build_guacamole_dsn
from ops_dsn import build_ops_dsn


def test_host_config_runtime_forwards_catalog_lifecycle_and_dsn_inputs():
    calls = []
    base = {"hosts": [{"name": "base"}]}
    dynamic = {"hosts": [{"name": "dynamic"}]}
    merged = {"hosts": [{"name": "merged"}]}
    resolved = {"hosts": [{"name": "resolved"}]}

    def read_config(path, missing_ok=True):
        calls.append(("read", path, missing_ok))
        return base if path == "base.json" else dynamic

    def load_config(config_path, dynamic_path, **kwargs):
        received_base = kwargs["read_config"](config_path, missing_ok=False)
        received_dynamic = kwargs["read_config"](dynamic_path, missing_ok=True)
        merged_config = kwargs["merge_configs"](received_base, received_dynamic)
        kwargs["validate_config"](merged_config)
        return kwargs["resolve_secret_refs"](merged_config)

    providers = {
        "_read_hosts_config_impl": read_config,
        "_merge_host_configs_impl": lambda received_base, received_dynamic: calls.append(
            ("merge", received_base, received_dynamic)
        ) or merged,
        "_resolve_host_secret_refs_impl": lambda config, **kwargs: calls.append(
            ("resolve", config, kwargs)
        ) or resolved,
        "_validate_winrm_catalog_impl": lambda config, **kwargs: calls.append(
            ("validate", config, kwargs)
        ),
        "_load_host_config_impl": load_config,
        "_build_ops_dsn_impl": build_ops_dsn,
        "_build_guacamole_dsn_impl": build_guacamole_dsn,
        "credential_ref_for_host": lambda host: "credential",
        "winrm_credentials_configured": lambda ref: True,
        "logging": SimpleNamespace(warning=lambda *args: calls.append(("warning", args))),
        "_catalog_bool_impl": lambda value: value,
        "_resolve_addresses_impl": lambda address, **kwargs: [address],
        "ipaddress": SimpleNamespace(ip_address=lambda value: value),
        "socket": SimpleNamespace(getaddrinfo=lambda *args, **kwargs: []),
        "CONFIG_PATH": "base.json",
        "DYNAMIC_CONFIG_PATH": "dynamic.json",
        "read_hosts_config": read_config,
        "merge_host_configs": lambda left, right: calls.append(
            ("merge", left, right)
        ) or merged,
        "validate_winrm_catalog": lambda config: calls.append(("validate-alias", config)),
        "resolve_host_secret_refs": lambda config: calls.append(
            ("resolve", config)
        ) or resolved,
        "MYSQL_DSN": None,
        "OPS_MYSQL_USER": "ops",
        "OPS_MYSQL_PASSWORD": "secret",
        "OPS_MYSQL_DATABASE": "ops_db",
        "MYSQL_HOSTNAME": "mysql",
        "MYSQL_PORT": 3306,
        "GUACAMOLE_MYSQL_DSN": None,
        "GUACAMOLE_MYSQL_USER": "guac",
        "GUACAMOLE_MYSQL_PASSWORD": "secret",
        "GUACAMOLE_MYSQL_DATABASE": "guac_db",
        "URL": SimpleNamespace(
            create=lambda *args, **kwargs: SimpleNamespace(
                render_as_string=lambda hide_password: "ops-rendered"
            )
        ),
        "make_url": lambda value: SimpleNamespace(
            set=lambda **kwargs: "derived-rendered"
        ),
    }
    runtime = create_host_config_runtime(providers)

    assert isinstance(runtime, HostConfigRuntime)
    assert runtime.load_config() is resolved
    assert runtime.build_ops_dsn() == "ops-rendered"
    assert runtime.build_guacamole_dsn() == "ops-rendered"
    assert calls[:5] == [
        ("read", "base.json", False),
        ("read", "dynamic.json", True),
        ("merge", base, dynamic),
        ("validate-alias", merged),
        ("resolve", merged),
    ]


def test_host_config_runtime_reads_mutable_paths_and_catalog_callbacks():
    calls = []
    providers = {
        "_read_hosts_config_impl": lambda path, missing_ok=True: calls.append(
            (path, missing_ok)
        ) or {"hosts": []},
        "_load_dynamic_config_impl": lambda path, **kwargs: kwargs["read_config"](
            path, missing_ok=True
        ),
        "DYNAMIC_CONFIG_PATH": "first.json",
        "read_hosts_config": lambda path, missing_ok=True: calls.append(
            ("alias", path, missing_ok)
        ) or {"hosts": []},
    }
    runtime = create_host_config_runtime(providers)
    providers["DYNAMIC_CONFIG_PATH"] = "second.json"

    assert runtime.load_dynamic_config() == {"hosts": []}
    assert calls == [("alias", "second.json", True)]
