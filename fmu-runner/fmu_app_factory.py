"""FastAPI application construction for the FMU Runner entrypoint."""

from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI


def create_app(*, lifespan: Any, routers: Iterable[Any] = ()) -> FastAPI:
    """Create the FMU Runner app and register routers in the supplied order."""
    app = FastAPI(title="FMU Runner", version="0.2.0", lifespan=lifespan)
    for router in routers:
        app.include_router(router)
    return app


__all__ = ["create_app"]
