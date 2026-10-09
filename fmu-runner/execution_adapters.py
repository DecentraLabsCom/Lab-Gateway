from typing import Optional

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


def reject_unsupported_remote_operation(feature_name: str, backend_mode: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=(
            f"{feature_name} is not available through FMU_BACKEND_MODE={backend_mode}. "
            "The remote FMU Executor does not expose this operation."
        ),
    )
