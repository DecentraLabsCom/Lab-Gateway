from contextlib import asynccontextmanager

from fastapi import APIRouter

from app_factory import create_app


def test_app_factory_preserves_fmu_runner_identity_and_lifespan():
    lifecycle = []

    @asynccontextmanager
    async def lifespan(_app):
        lifecycle.append("started")
        yield
        lifecycle.append("stopped")

    router = APIRouter()

    @router.get("/contract")
    async def contract_route():
        return {"ok": True}

    app = create_app(lifespan=lifespan, routers=(router,))

    assert app.title == "FMU Runner"
    assert app.version == "0.2.0"
    assert "/contract" in app.openapi()["paths"]

    import asyncio

    async def exercise_lifespan():
        async with app.router.lifespan_context(app):
            assert lifecycle == ["started"]

    asyncio.run(exercise_lifespan())
    assert lifecycle == ["started", "stopped"]
