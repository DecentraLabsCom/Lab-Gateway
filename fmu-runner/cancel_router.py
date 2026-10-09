"""Reservation-scoped remote simulation cancellation route."""

from typing import Any

from fastapi import APIRouter, Depends


def create_cancel_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    reject_unsupported_operation: Any,
    get_station_backend: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/simulations/{sim_id}/cancel")
    async def cancel_simulation(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        if get_station_backend is None:
            reject_unsupported_operation("Simulation cancel endpoint")
        return await get_station_backend().cancel_authorized_simulation(claims=claims, sim_id=sim_id)

    return router
