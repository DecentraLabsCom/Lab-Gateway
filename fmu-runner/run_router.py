"""HTTP composition for executing a reservation-scoped FMU simulation."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from simulation_request import SimulationRequest


def create_run_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_backend_mode: Any,
    get_station_backend: Any,
    simulation_request_payload: Any,
    extract_authorization_header: Any,
    record_browser_session_started: Any,
    ensure_local_execution_backend: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    enforce_requested_reservation: Any,
    resolve_fmu_path: Any,
    parse_simulation_options: Any,
    resolve_fmi_type: Any,
    acquire_slot: Any,
    new_simulation_id: Any,
    monotonic: Any,
    submit_simulation: Any,
    track_running_future: Any,
    shutdown_executor: Any,
    finalize_tracking: Any,
    save_history: Any,
    logger: Any,
) -> APIRouter:
    """Build the run route while keeping backend and lifecycle dependencies injected."""
    router = APIRouter()

    @router.post("/api/v1/simulations/run")
    async def run_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        """Execute an FMU simulation and return results."""
        enforce_fmu_claim(claims)
        if get_backend_mode() == "station":
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
                # The gateway id is the durable observation key. Ignore any
                # executor identifier returned by Station.
                result["simId"] = sim_id
            return result

        ensure_local_execution_backend("Simulation run endpoint")

        fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
        claims_lab_id = get_claim_lab_id(claims)
        request_lab_id = normalize_lab_id(req.labId)
        if claims_lab_id and request_lab_id and claims_lab_id != request_lab_id:
            raise HTTPException(status_code=403, detail="JWT not authorised for requested labId")
        lab_id = request_lab_id or claims_lab_id or "unknown"
        enforce_requested_reservation(claims, req.reservationKey)

        if req.labId is None and claims_lab_id:
            req.labId = claims_lab_id

        if not fmu_filename:
            raise HTTPException(status_code=400, detail="Cannot determine FMU file name from JWT or request")

        fmu_path = resolve_fmu_path(fmu_filename)
        execution_options = parse_simulation_options(req.options, claims)
        start_time = execution_options.start_time
        stop_time = execution_options.stop_time
        step_size = execution_options.step_size
        timeout = execution_options.timeout

        fmi_type = resolve_fmi_type(execution_options.fmi_type, fmu_path)
        solver_name = execution_options.solver_name

        acquire_slot(lab_id)

        sim_id = new_simulation_id()
        t0 = monotonic()
        future = None
        job_executor = None
        try:
            # Durable observation is the acceptance gate. The executor is not
            # released until it succeeds, so a failed observation cannot race
            # with work that has already started.
            await record_browser_session_started(request, claims, sim_id)
            job_executor, future = submit_simulation(
                str(fmu_path),
                start_time,
                stop_time,
                step_size,
                req.parameters,
                timeout,
                fmi_type,
                solver_name,
            )
            if future is None:
                raise RuntimeError("simulation executor returned no future")
            track_running_future(sim_id, future, lab_id, claims, job_executor)
            try:
                sim_result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
            except asyncio.TimeoutError as exc:
                if not future.done():
                    future.cancel()
                shutdown_executor(job_executor, force=True)
                raise HTTPException(status_code=504, detail="Simulation timed out") from exc
        except HTTPException:
            raise
        except Exception as exc:
            if future is None and job_executor is not None:
                shutdown_executor(job_executor, force=True)
            logger.error(
                "Simulation failed for lab %s: %s",
                str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
                type(exc).__name__,
            )
            raise HTTPException(status_code=500, detail="Simulation failed") from exc
        finally:
            finalize_tracking(sim_id, lab_id)

        elapsed = round(monotonic() - t0, 3)
        logger.info(
            "Simulation completed for lab %s in %.3fs",
            str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
            elapsed,
        )

        await save_history(
            sim_id,
            lab_id,
            claims,
            fmu_filename,
            fmi_type,
            req.parameters,
            req.options,
            sim_result,
            elapsed,
        )

        return {
            "status": "completed",
            "simId": sim_id,
            "simulationTime": elapsed,
            "fmiType": fmi_type,
            **sim_result,
        }

    return router
