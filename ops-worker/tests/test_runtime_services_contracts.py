from runtime_services import RuntimeServices, create_runtime_services


def test_create_runtime_services_preserves_power_then_reservation_order():
    calls = []
    power_state = object()
    reservation = object()

    services = create_runtime_services(
        power_factory=lambda **kwargs: calls.append(("power", kwargs)) or power_state,
        power_arguments={"db_engine": "db", "record_operation": "record"},
        reservation_factory=lambda engine, registry: calls.append(
            ("reservation", engine, registry)
        ) or reservation,
        reservation_engine="db",
        reservation_registry="hosts",
    )

    assert isinstance(services, RuntimeServices)
    assert services.power_state is power_state
    assert services.reservation_automator is reservation
    assert calls == [
        ("power", {"db_engine": "db", "record_operation": "record"}),
        ("reservation", "db", "hosts"),
    ]


def test_worker_publishes_power_and_reservation_aliases_from_runtime_services():
    import worker

    source = open(worker.__file__, encoding="utf-8").read()

    assert "_RUNTIME_SERVICES = create_runtime_services(" in source
    assert "_POWER_RUNTIME_STATE = _RUNTIME_SERVICES.power_state" in source
    assert "RESERVATION_AUTOMATOR = _RUNTIME_SERVICES.reservation_automator" in source
