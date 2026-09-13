"""HTTP composition for the reservation-scoped FMU NDJSON stream."""

import asyncio
import json
from concurrent.futures import Future
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from simulation_request import SimulationRequest


def create_stream_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_backend_mode: Any,
    stream_station_simulation: Any,
    ensure_local_execution_backend: Any,
    get_claim_lab_id: Any,
    normalize_lab_id: Any,
    enforce_requested_reservation: Any,
    resolve_fmu_path: Any,
    parse_simulation_options: Any,
    resolve_fmi_type: Any,
    new_simulation_id: Any,
    monotonic: Any,
    acquire_slot: Any,
    record_browser_session_started: Any,
    submit_simulation: Any,
    track_running_future: Any,
    shutdown_executor: Any,
    finalize_tracking: Any,
    iter_result_chunks: Any,
    build_completed_event: Any,
    stream_error_payload: Any,
    save_history: Any,
    sleep: Any,
    logger: Any,
) -> APIRouter:
    """Build the stream route with execution and observation dependencies injected."""
    router = APIRouter()

    @router.post("/api/v1/simulations/stream")
    async def stream_simulation(
        req: SimulationRequest,
        request: Request,
        claims: dict = Depends(verify_jwt),
    ):
        """Execute a simulation and stream results as newline-delimited JSON."""
        enforce_fmu_claim(claims)
        if get_backend_mode() == "station":
            return await stream_station_simulation(request, req, claims)
        ensure_local_execution_backend("Simulation stream endpoint")

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
        sim_id = new_simulation_id()

        async def event_stream():
            t0 = monotonic()
            future: Future | None = None
            job_executor: Any = None
            acquire_slot(lab_id)
            try:
                # Observation is the durable acceptance gate; only then is the
                # worker released and the ``started`` event exposed.
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
                yield json.dumps({"type": "started", "simId": sim_id}) + "\n"

                while not future.done():
                    elapsed = round(monotonic() - t0, 1)
                    if elapsed >= timeout:
                        future.cancel()
                        shutdown_executor(job_executor, force=True)
                        yield json.dumps({
                            "type": "error",
                            "simId": sim_id,
                            "detail": "Simulation timed out",
                        }) + "\n"
                        return
                    yield json.dumps({"type": "progress", "elapsedSeconds": elapsed}) + "\n"
                    await sleep(1)

                sim_result = future.result()
                for chunk in iter_result_chunks(sim_result):
                    yield json.dumps(chunk) + "\n"

                elapsed = round(monotonic() - t0, 3)
                yield json.dumps(build_completed_event(
                    sim_id=sim_id,
                    simulation_time=elapsed,
                    fmi_type=fmi_type,
                    simulation_result=sim_result,
                )) + "\n"
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
            except Exception as exc:
                logger.exception(
                    "Streaming simulation failed for lab %s sim_id=%s",
                    str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
                    sim_id,
                )
                yield json.dumps(stream_error_payload(exc, sim_id=sim_id)) + "\n"
            finally:
                finalize_tracking(sim_id, lab_id)

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    return router


__all__ = ["create_stream_router"]
