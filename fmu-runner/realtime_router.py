"""WebSocket route composition for realtime FMU sessions."""

from typing import Any

from fastapi import APIRouter, WebSocket


def create_realtime_router(*, get_realtime_manager: Any) -> APIRouter:
    """Build public and internal realtime session routes."""
    router = APIRouter()

    @router.websocket("/api/v1/fmu/sessions")
    async def fmu_realtime_sessions(websocket: WebSocket):
        await get_realtime_manager().handle_websocket(websocket, internal=False)

    @router.websocket("/internal/fmu/sessions")
    async def fmu_realtime_sessions_internal(websocket: WebSocket):
        await get_realtime_manager().handle_websocket(websocket, internal=True)

    return router


__all__ = ["create_realtime_router"]
