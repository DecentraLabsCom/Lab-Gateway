import pytest
from fastapi import HTTPException

from execution_adapters import reject_unsupported_remote_operation, simulation_request_payload


def test_simulation_request_payload_preserves_request_fields():
    parameters = {"mass": 1.5}
    options = {"stopTime": 2.0}

    payload = simulation_request_payload(
        reservation_key="reservation-1",
        lab_id="lab-1",
        parameters=parameters,
        options=options,
        sim_id="sim-1",
    )

    assert payload == {
        "reservationKey": "reservation-1",
        "labId": "lab-1",
        "parameters": parameters,
        "options": options,
        "simId": "sim-1",
    }


def test_simulation_request_payload_omits_empty_simulation_id():
    payload = simulation_request_payload(
        reservation_key=None,
        lab_id=None,
        parameters={},
        options={},
        sim_id=None,
    )

    assert payload == {
        "reservationKey": None,
        "labId": None,
        "parameters": {},
        "options": {},
    }


def test_reject_unsupported_remote_operation_returns_not_implemented():
    with pytest.raises(HTTPException) as error:
        reject_unsupported_remote_operation("Simulation history endpoint", "station")

    assert error.value.status_code == 501
    assert error.value.detail == (
        "Simulation history endpoint is not available through FMU_BACKEND_MODE=station. "
        "The remote FMU Executor does not expose this operation."
    )
