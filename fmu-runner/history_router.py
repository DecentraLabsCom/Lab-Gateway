import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query


def create_history_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    ensure_local_execution_backend: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    claim_reservation_key: Any,
    get_history_db_path: Any,
    list_history: Any,
    get_history_result: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/simulations/history")
    async def get_history(
        labId: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        ensure_local_execution_backend("Simulation history endpoint")
        claim_lab_id = get_claim_lab_id(claims)
        if not claim_lab_id:
            raise HTTPException(status_code=403, detail="Token has no authorised labId")
        requested_lab_id = normalize_lab_id(labId)
        if requested_lab_id and requested_lab_id != claim_lab_id:
            raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")
        effective_lab_id = requested_lab_id or claim_lab_id
        reservation_key = claim_reservation_key(claims)

        rows = await list_history(
            get_history_db_path(),
            lab_id=effective_lab_id,
            reservation_key=reservation_key,
            puc_hash=str(claims.get("pucHash") or "").strip().lower(),
            limit=limit,
            offset=offset,
        )
        return {"simulations": rows}

    @router.get("/api/v1/simulations/{sim_id}/result")
    async def get_simulation_result(sim_id: str, claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        ensure_local_execution_backend("Simulation result endpoint")
        claim_lab_id = get_claim_lab_id(claims)
        if not claim_lab_id:
            raise HTTPException(status_code=403, detail="Token has no authorised labId")

        row = await get_history_result(
            get_history_db_path(),
            sim_id=sim_id,
            lab_id=claim_lab_id,
            reservation_key=claim_reservation_key(claims),
            puc_hash=str(claims.get("pucHash") or "").strip().lower(),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Simulation not found")
        result = dict(row)
        for key in ("parameters", "options", "result"):
            if result.get(key):
                result[key] = json.loads(result[key])
        return result

    return router