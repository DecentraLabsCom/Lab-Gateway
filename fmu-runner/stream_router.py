"""HTTP facade for a reservation-scoped FMU result stream."""

from typing import Any

from fastapi import APIRouter, Depends, Request

from simulation_request import SimulationRequest


def create_stream_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    stream_station_simulation: Any,
) -> APIRouter:
    """Build a streaming route that delegates execution to the Executor."""
    router = APIRouter()

    @router.post("/api/v1/simulations/stream")
    async def stream_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        return await stream_station_simulation(request, req, claims)

    return router


__all__ = ["create_stream_router"]
