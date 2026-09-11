from typing import Any, Optional

from fastapi import HTTPException


def simulation_request_payload(
    *,
    reservation_key: Optional[str],
    lab_id: Optional[str],
    parameters: dict,
    options: dict,
    sim_id: Optional[str] = None,
) -> dict:
    payload = {
        "reservationKey": reservation_key,
        "labId": lab_id,
        "parameters": parameters,
        "options": options,
    }
    if sim_id:
        payload["simId"] = sim_id
    return payload


def ensure_local_execution_backend(feature_name: str, backend: Any) -> None:
    if backend.supports_local_execution:
        return
    raise HTTPException(
        status_code=501,
        detail=(
            f"{feature_name} is not wired for FMU_BACKEND_MODE={backend.mode}. "
            "Use FMU_BACKEND_MODE=station in production, or explicitly set "
            "FMU_BACKEND_MODE=local and FMU_LOCAL_DEV_MODE=true for isolated development."
        ),
    )