from runtime_state import RuntimeState, create_runtime_state, replace_host_registry


def test_replace_host_registry_contract_publishes_registry_and_updates_automator():
    calls = []
    registry = object()
    class Automator:
        registry: object | None = None

    automator = Automator()

    replace_host_registry(
        registry,
        set_registry=lambda value: calls.append(("set", value)),
        reservation_automator=automator,
    )

    assert calls == [("set", registry)]
    assert automator.registry is registry


def test_create_runtime_state_contract_preserves_catalog_and_engine_order():
    calls = []

    def load_hosts():
        calls.append("hosts")
        return {"hosts": [{"name": "lab-01"}]}

    lock = object()

    def registry_factory(config):
        calls.append(("registry", config))
        return {"registry": config}

    def build_ops_dsn():
        calls.append("ops-dsn")
        return "mysql://ops"

    def build_guacamole_dsn():
        calls.append("guac-dsn")
        return None

    def create_engine(dsn, *, pool_pre_ping):
        calls.append(("engine", dsn, pool_pre_ping))
        return {"dsn": dsn}

    def lock_factory():
        calls.append("lock")
        return lock

    state = create_runtime_state(
        load_hosts=load_hosts,
        registry_factory=registry_factory,
        build_ops_dsn=build_ops_dsn,
        build_guacamole_dsn=build_guacamole_dsn,
        create_engine=create_engine,
        lock_factory=lock_factory,
    )

    assert isinstance(state, RuntimeState)
    assert state.hosts == {"registry": {"hosts": [{"name": "lab-01"}]}}
    assert state.ops_dsn == "mysql://ops"
    assert state.db_engine == {"dsn": "mysql://ops"}
    assert state.guacamole_dsn is None
    assert state.guacamole_db_engine is None
    assert state.hosts_lock is lock
    assert calls == [
        "lock",
        "hosts",
        ("registry", {"hosts": [{"name": "lab-01"}]}),
        "ops-dsn",
        ("engine", "mysql://ops", True),
        "guac-dsn",
    ]


def test_create_runtime_state_contract_skips_engine_factory_without_dsn():
    calls = []

    state = create_runtime_state(
        load_hosts=lambda: {"hosts": []},
        registry_factory=lambda config: config,
        build_ops_dsn=lambda: None,
        build_guacamole_dsn=lambda: "",
        create_engine=lambda *_args, **_kwargs: calls.append("unexpected"),
    )

    assert state.db_engine is None
    assert state.guacamole_db_engine is None
    assert calls == []


def test_worker_uses_runtime_state_factory_without_inline_engine_initialization():
    import worker

    source = open(worker.__file__, encoding="utf-8").read()

    assert "create_runtime_state(" in source
    assert "DB_ENGINE: Optional[Engine] = create_engine(" not in source
    assert "HOSTS = _RUNTIME_STATE.hosts" in source
    assert "HOSTS_LOCK = _RUNTIME_STATE.hosts_lock" in source
    assert "OPS_DSN = _RUNTIME_STATE.ops_dsn" in source
    assert "DB_ENGINE: Optional[Engine] = _RUNTIME_STATE.db_engine" in source
    assert "GUACAMOLE_DSN = _RUNTIME_STATE.guacamole_dsn" in source
    assert "GUACAMOLE_DB_ENGINE: Optional[Engine] = _RUNTIME_STATE.guacamole_db_engine" in source
    assert worker._RUNTIME_STATE.hosts is not None


def test_worker_uses_runtime_config_snapshot_for_paths_and_database_inputs():
    import worker

    source = open(worker.__file__, encoding="utf-8").read()

    assert "load_runtime_paths(" in source
    assert "publish_runtime_paths(_RUNTIME_PATHS, globals())" in source
    assert "MYSQL_PORT = int(os.getenv" not in source
    assert "OPS_MYSQL_PASSWORD = _env_or_secret_file(" not in source
