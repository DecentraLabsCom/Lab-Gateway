import asyncio

from lifecycle import create_lifespan


def test_lifecycle_preserves_start_order_and_shutdown_order():
    events = []

    class Manager:
        async def start(self):
            events.append("manager.start")

        async def stop(self):
            events.append("manager.stop")

    manager = Manager()

    async def init_db():
        events.append("init_db")

    async def preload_jwks():
        events.append("preload_jwks")

    def shutdown_executor(executor):
        events.append(("shutdown_executor", executor))

    async def cleanup_temp_files():
        events.append("cleanup_temp_files")

    lifespan = create_lifespan(
        init_db=init_db,
        preload_jwks=preload_jwks,
        get_realtime_manager=lambda: manager,
        get_executor=lambda: "executor",
        shutdown_executor=shutdown_executor,
        cleanup_temp_files=cleanup_temp_files,
    )

    async def exercise():
        async with lifespan(object()):
            events.append("ready")

    asyncio.run(exercise())

    assert events == [
        "init_db",
        "preload_jwks",
        "manager.start",
        "ready",
        "manager.stop",
        ("shutdown_executor", "executor"),
        "cleanup_temp_files",
    ]


def test_lifecycle_skips_optional_manager_without_skipping_cleanup():
    events = []

    async def cleanup_temp_files():
        events.append("cleanup")

    lifespan = create_lifespan(
        init_db=lambda: _record(events, "init"),
        preload_jwks=lambda: _record(events, "preload"),
        get_realtime_manager=lambda: None,
        get_executor=lambda: "executor",
        shutdown_executor=lambda executor: events.append(("shutdown", executor)),
        cleanup_temp_files=cleanup_temp_files,
    )

    async def exercise():
        async with lifespan(object()):
            events.append("ready")

    asyncio.run(exercise())

    assert events == ["init", "preload", "ready", ("shutdown", "executor"), "cleanup"]


def test_lifecycle_initializes_runtime_before_other_startup_work():
    events = []

    async def initialize_runtime():
        events.append("initialize_runtime")

    async def init_db():
        events.append("init_db")

    async def preload_jwks():
        events.append("preload_jwks")

    lifespan = create_lifespan(
        initialize_runtime=initialize_runtime,
        init_db=init_db,
        preload_jwks=preload_jwks,
        get_realtime_manager=lambda: None,
        get_executor=lambda: "executor",
        shutdown_executor=lambda _executor: events.append("shutdown_executor"),
        cleanup_temp_files=lambda: _record(events, "cleanup"),
    )

    async def exercise():
        async with lifespan(object()):
            events.append("ready")

    asyncio.run(exercise())

    assert events == [
        "initialize_runtime",
        "init_db",
        "preload_jwks",
        "ready",
        "shutdown_executor",
        "cleanup",
    ]


async def _record(events, value):
    events.append(value)
