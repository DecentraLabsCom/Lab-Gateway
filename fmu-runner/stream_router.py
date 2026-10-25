"""HTTP facade for a reservation-scoped FMU result stream."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from simulation_access_policy import AccessDenied, validate_writes
from simulation_request import SimulationRequest


async def stream_authorized_simulation(
    *,
    req: SimulationRequest,
    request: Request,
    claims: dict,
    enforce_fmu_claim: Any,
    stream_station_simulation: Any,
    get_effective_policy: Any = None,
):
    """Apply the standard reservation and AAS checks before opening a stream."""
    enforce_fmu_claim(claims)
    access_policy = None
    if get_effective_policy is not None:
        access_policy = await get_effective_policy(claims)
        if not isinstance(access_policy, dict) or not isinstance(access_policy.get("variables"), dict):
            raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
        try:
            validate_writes(access_policy, req.parameters, phase="initialization")
            for event in req.inputSchedule:
                validate_writes(access_policy, event.get("values", {}), phase="runtime")
        except AccessDenied as exc:
            raise HTTPException(
                status_code=403,
                detail="Variable access denied by the effective FMU policy",
            ) from exc
    return await stream_station_simulation(request, req, claims, access_policy)


def create_stream_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    stream_station_simulation: Any,
    get_effective_policy: Any = None,
) -> APIRouter:
    """Build a streaming route that delegates execution to the Executor."""
    router = APIRouter()

    @router.post("/api/v1/simulations/stream")
    async def stream_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        return await stream_authorized_simulation(
            req=req,
            request=request,
            claims=claims,
            enforce_fmu_claim=enforce_fmu_claim,
            stream_station_simulation=stream_station_simulation,
            get_effective_policy=get_effective_policy,
        )

    return router


__all__ = ["create_stream_router", "stream_authorized_simulation"]
