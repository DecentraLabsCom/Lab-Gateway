"""HTTP composition for cancelling an active local FMU simulation."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException


def create_cancel_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    ensure_local_execution_backend: Any,
    get_running_entry: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    claim_reservation_key: Any,
    shutdown_executor: Any,
    finalize_tracking: Any,
) -> APIRouter:
    """Build the cancellation route while keeping runtime dependencies injected."""
    router = APIRouter()

    @router.post("/api/v1/simulations/{sim_id}/cancel")
    async def cancel_simulation(sim_id: str, claims: dict = Depends(verify_jwt)):
        """Attempt to cancel a running simulation by its ID."""
        enforce_fmu_claim(claims)
        ensure_local_execution_backend("Simulation cancel endpoint")

        entry = get_running_entry(sim_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Simulation not found or already finished")

        future, lab_id, reservation_key, puc_hash, job_executor = entry
        if get_claim_lab_id(claims) != normalize_lab_id(lab_id):
            raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")
        if claim_reservation_key(claims) != reservation_key:
            raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")
        if str(claims.get("pucHash") or "").strip().lower() != puc_hash:
            raise HTTPException(status_code=403, detail="Token is not authorised for requested simulation")

        future.cancel()
        shutdown_executor(job_executor, force=True)
        finalize_tracking(sim_id)
        return {"status": "cancelled"}

    return router
