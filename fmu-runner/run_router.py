"""HTTP facade for a reservation-scoped FMU simulation."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from simulation_access_policy import AccessDenied, filter_fmi_values, validate_writes
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
    get_effective_policy: Any = None,
    reject_unsupported_operation: Any = None,
) -> APIRouter:
    """Build the run route; the Gateway authorizes and forwards the request."""
    router = APIRouter()

    async def _policy(claims: dict):
        if get_effective_policy is None:
            return None
        policy = await get_effective_policy(claims)
        if not isinstance(policy, dict) or not isinstance(policy.get("variables"), dict):
            raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
        return policy

    def _authorize_values(policy, values, *, phase: str):
        if policy is None:
            return
        try:
            validate_writes(policy, values, phase=phase)
        except AccessDenied as exc:
            raise HTTPException(status_code=403, detail="Variable access denied by the effective FMU policy") from exc

    def _filter_result(policy, result):
        return filter_fmi_values(policy, result) if policy is not None else result

    @router.post("/api/v1/simulations/run")
    async def run_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        _authorize_values(access_policy, req.parameters, phase="initialization")
        for event in req.inputSchedule:
            _authorize_values(access_policy, event.get("values", {}), phase="runtime")
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
        return _filter_result(access_policy, result)

    @router.post("/api/v1/simulations/jobs", status_code=202)
    async def submit_simulation_job(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        _authorize_values(access_policy, req.parameters, phase="initialization")
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
        return _filter_result(access_policy, _public_job_response(result, sim_id))

    @router.post("/api/v1/simulations/batches", status_code=202)
    async def submit_simulation_batch(
        req: BatchSimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims)
        access_policy = await _policy(claims)
        for scenario in req.scenarios:
            _authorize_values(access_policy, scenario.parameters, phase="initialization")
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
        return _filter_result(access_policy, _public_job_response(result, batch_id))

    return router


def _public_job_response(payload: dict, sim_id: str) -> dict:
    result = dict(payload)
    result["id"] = sim_id
    result["simId"] = sim_id
    result["statusUrl"] = f"/api/v1/simulations/{sim_id}"
    result["resultUrl"] = f"/api/v1/simulations/{sim_id}/result"
    return result


__all__ = ["create_run_router"]
