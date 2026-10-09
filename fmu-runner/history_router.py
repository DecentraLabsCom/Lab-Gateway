"""Reservation-scoped simulation status, history, and result routes."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query


def create_history_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    reject_unsupported_operation: Any,
    get_station_backend: Any = None,
) -> APIRouter:
    router = APIRouter()

    def _backend():
        if get_station_backend is None:
            reject_unsupported_operation("Simulation history endpoint")
        return get_station_backend()

    @router.get("/api/v1/simulations/history")
    async def get_history(
        labId: Optional[str] = Query(None),
        reservationKey: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100000),
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        backend = _backend()
        return await backend.get_authorized_simulation_history(
            claims=claims,
            requested_lab_id=labId,
            requested_reservation_key=reservationKey,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/v1/simulations/{sim_id}/result")
    async def get_simulation_result(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        backend = _backend()
        return await backend.get_authorized_simulation_result(claims=claims, sim_id=sim_id)

    @router.get("/api/v1/simulations/{sim_id}")
    async def get_simulation_status(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        backend = _backend()
        return await backend.get_authorized_simulation_status(claims=claims, sim_id=sim_id)

    return router


__all__ = ["create_history_router"]
