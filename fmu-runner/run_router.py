"""HTTP facade for a reservation-scoped FMU simulation."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from simulation_request import BatchSimulationRequest, SimulationRequest


def create_run_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_station_backend: Any,
    simulation_request_payload: Any,
    extract_authorization_header: Any,
    record_browser_session_started: Any,
    new_simulation_id: Any,
    reject_unsupported_operation: Any = None,
) -> APIRouter:
    """Build the run route; the Gateway authorizes and forwards the request."""
    router = APIRouter()

    @router.post("/api/v1/simulations/run")
    async def run_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        station_backend = get_station_backend()
        station_backend.build_authorized_context(
            claims=claims,
            requested_lab_id=req.labId,
            requested_reservation_key=req.reservationKey,
        )
        sim_id = new_simulation_id()
        await record_browser_session_started(request, claims, sim_id)
        result = await station_backend.run_authorized_simulation(
            claims=claims,
            request_payload=simulation_request_payload(req, sim_id),
            authorization=extract_authorization_header(request),
        )
        if isinstance(result, dict):
            result = dict(result)
            # The Gateway id is the durable observation key.
            result["simId"] = sim_id
        return result

    @router.post("/api/v1/simulations/jobs", status_code=202)
    async def submit_simulation_job(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        station_backend = get_station_backend()
        station_backend.build_authorized_context(
            claims=claims,
            requested_lab_id=req.labId,
            requested_reservation_key=req.reservationKey,
        )
        submit = getattr(station_backend, "submit_authorized_job", None)
        if submit is None:
            if reject_unsupported_operation:
                reject_unsupported_operation("Asynchronous simulation jobs")
            raise HTTPException(status_code=501, detail="Asynchronous simulation jobs are unavailable")
        sim_id = new_simulation_id()
        await record_browser_session_started(request, claims, sim_id)
        result = await submit(
            claims=claims,
            request_payload=simulation_request_payload(req, sim_id),
            authorization=extract_authorization_header(request),
        )
        return _public_job_response(result, sim_id)

    @router.post("/api/v1/simulations/batches", status_code=202)
    async def submit_simulation_batch(
        req: BatchSimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        station_backend = get_station_backend()
        station_backend.build_authorized_context(
            claims=claims,
            requested_lab_id=req.labId,
            requested_reservation_key=req.reservationKey,
        )
        submit = getattr(station_backend, "submit_authorized_batch", None)
        if submit is None:
            if reject_unsupported_operation:
                reject_unsupported_operation("Batch simulations")
            raise HTTPException(status_code=501, detail="Batch simulations are unavailable")
        batch_id = new_simulation_id()
        await record_browser_session_started(request, claims, batch_id)
        result = await submit(
            claims=claims,
            request_payload={
                "labId": req.labId,
                "reservationKey": req.reservationKey,
                "batchId": batch_id,
                "options": req.options,
                "scenarios": [scenario.model_dump() for scenario in req.scenarios],
            },
            authorization=extract_authorization_header(request),
        )
        return _public_job_response(result, batch_id)

    return router


def _public_job_response(payload: dict, sim_id: str) -> dict:
    result = dict(payload)
    result["id"] = sim_id
    result["simId"] = sim_id
    result["statusUrl"] = f"/api/v1/simulations/{sim_id}"
    result["resultUrl"] = f"/api/v1/simulations/{sim_id}/result"
    return result


__all__ = ["create_run_router"]
