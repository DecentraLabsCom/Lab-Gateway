"""Reservation-scoped simulation status, history, and result routes."""

from typing import Any, Callable, NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from simulation_access_policy import filter_fmi_values


def create_history_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    reject_unsupported_operation: Callable[[str], NoReturn],
    get_station_backend: Optional[Callable[..., Any]] = None,
    get_effective_policy: Any = None,
) -> APIRouter:
    router = APIRouter()

    async def _policy(claims: dict):
        if get_effective_policy is None:
            return None
        policy = await get_effective_policy(claims)
        if not isinstance(policy, dict) or not isinstance(policy.get("variables"), dict):
            raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
        return policy

    def _filter(policy, payload):
        return filter_fmi_values(policy, payload) if policy is not None else payload

    def _backend(operation_name: str):
        if get_station_backend is None:
            reject_unsupported_operation(operation_name)
        return get_station_backend(operation_name)

    @router.get("/api/v1/simulations/history")
    async def get_history(
        labId: Optional[str] = Query(None),
        reservationKey: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100000),
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        backend = _backend("Simulation history endpoint")
        result = await backend.get_authorized_simulation_history(
            claims=claims,
            requested_lab_id=labId,
            requested_reservation_key=reservationKey,
            limit=limit,
            offset=offset,
        )
        return _filter(access_policy, result)

    @router.get("/api/v1/simulations/{sim_id}/result")
    async def get_simulation_result(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        backend = _backend("Simulation result endpoint")
        result = await backend.get_authorized_simulation_result(claims=claims, sim_id=sim_id)
        return _filter(access_policy, result)

    @router.get("/api/v1/simulations/{sim_id}")
    async def get_simulation_status(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        backend = _backend("Simulation status endpoint")
        result = await backend.get_authorized_simulation_status(claims=claims, sim_id=sim_id)
        return _filter(access_policy, result)

    return router


__all__ = ["create_history_router"]
