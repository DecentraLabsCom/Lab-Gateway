from power_runtime_factory import PowerRuntimeState, create_power_runtime


def test_create_power_runtime_contract_preserves_store_wiring_and_success_path():
    calls = []
    extensions = {}
    runtime = object()
    credential_store = type("CredentialStore", (), {"get": lambda self, key: key})()

    state = create_power_runtime(
        extensions=extensions,
        db_engine="ops-engine",
        config_path="power.json",
        status_cache_ttl_seconds=5,
        operation_store_factory=lambda engine: calls.append(("operation-store", engine)) or "operations",
        credential_store_factory=lambda: calls.append("credential-store") or credential_store,
        runtime_from_path=lambda *args, **kwargs: calls.append(("from-path", args, kwargs)) or runtime,
        runtime_from_config=lambda *args, **kwargs: calls.append(("from-config", args, kwargs)) or "fallback",
        record_operation="record",
        logger=type("Logger", (), {"error": lambda *_args, **_kwargs: calls.append("error")})(),
    )

    assert isinstance(state, PowerRuntimeState)
    assert state.operation_store == "operations"
    assert state.credential_store is credential_store
    assert state.runtime is runtime
    assert extensions == {
        "power_credential_store": credential_store,
        "power_runtime": runtime,
    }
    assert calls == [
        ("operation-store", "ops-engine"),
        "credential-store",
        ("from-path", ("power.json",), {
            "record_operation": "record",
            "operation_store": "operations",
            "credential_resolver": credential_store.get,
            "status_cache_ttl_seconds": 5,
        }),
    ]


def test_create_power_runtime_contract_skips_operation_store_without_db_and_falls_back_closed():
    calls = []
    extensions = {}
    credential_store = type("CredentialStore", (), {"get": lambda self, key: key})()

    def runtime_from_path(*_args, **_kwargs):
        calls.append("from-path")
        raise RuntimeError("secret catalog details")

    state = create_power_runtime(
        extensions=extensions,
        db_engine=None,
        config_path="power.json",
        status_cache_ttl_seconds=0,
        operation_store_factory=lambda _engine: calls.append("unexpected-store"),
        credential_store_factory=lambda: credential_store,
        runtime_from_path=runtime_from_path,
        runtime_from_config=lambda *args, **kwargs: calls.append(("from-config", args, kwargs)) or "empty",
        record_operation="record",
        logger=type("Logger", (), {"error": lambda *_args, **_kwargs: calls.append("error")})(),
    )

    assert state.operation_store is None
    assert state.runtime == "empty"
    assert extensions["power_runtime"] == "empty"
    assert calls[0] == "from-path"
    assert calls[1] == "error"
    assert calls[2][0] == "from-config"
    assert calls[2][1] == ({"controllers": [], "outlets": [], "policies": []},)
    assert "secret catalog details" not in str(calls)
