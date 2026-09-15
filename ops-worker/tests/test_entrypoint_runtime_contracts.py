from entrypoint import configure_logging, run


def test_configure_logging_contract_uses_requested_level_and_format():
    calls = []

    configure_logging(
        level="debug",
        basic_config=lambda **kwargs: calls.append(kwargs),
    )

    assert calls == [{
        "level": "DEBUG",
        "format": "%(asctime)s %(levelname)s %(message)s",
    }]


def test_run_contract_preserves_startup_order_and_waitress_arguments():
    calls = []
    app = object()
    hosts = [{"name": "station-01"}]

    run(
        configure_logging=lambda: calls.append("logging"),
        refresh_trust_store=lambda received: calls.append(("trust", received)),
        hosts=hosts,
        start_scheduler=lambda: calls.append("scheduler"),
        bind="127.0.0.1",
        port=9876,
        serve=lambda received_app, host, port: calls.append(
            ("serve", received_app, host, port)
        ),
        app=app,
    )

    assert calls == [
        "logging",
        ("trust", hosts),
        "scheduler",
        ("serve", app, "127.0.0.1", 9876),
    ]


def test_run_shuts_down_the_scheduler_after_waitress_returns():
    calls = []
    app = object()

    class Scheduler:
        def shutdown(self, *, wait):
            calls.append(("shutdown", wait))

    scheduler = Scheduler()

    result = run(
        configure_logging=lambda: calls.append("logging"),
        refresh_trust_store=lambda _hosts: calls.append("trust"),
        hosts=[],
        start_scheduler=lambda: scheduler,
        bind="127.0.0.1",
        port=9876,
        serve=lambda received_app, host, port: calls.append(
            ("serve", received_app, host, port)
        ) or "served",
        app=app,
    )

    assert result == "served"
    assert calls == [
        "logging",
        "trust",
        ("serve", app, "127.0.0.1", 9876),
        ("shutdown", True),
    ]


def test_worker_delegates_process_startup_to_entrypoint_module():
    import worker

    source = open(worker.__file__, encoding="utf-8").read()

    assert "from entrypoint import" in source
    assert "create_entrypoint_runtime" in source
    assert "def main(" not in source
    assert "serve(APP, host=bind, port=port)" not in source
