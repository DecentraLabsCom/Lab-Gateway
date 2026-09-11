from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from execution_adapters import ensure_local_execution_backend, simulation_request_payload


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


def test_ensure_local_execution_backend_accepts_supported_backend():
    backend = SimpleNamespace(mode="local", supports_local_execution=True)

    assert ensure_local_execution_backend("Simulation run endpoint", backend) is None


def test_ensure_local_execution_backend_rejects_unsupported_backend():
    backend = SimpleNamespace(mode="station", supports_local_execution=False)

    with pytest.raises(HTTPException) as error:
        ensure_local_execution_backend("Simulation run endpoint", backend)

    assert error.value.status_code == 501
    assert error.value.detail == (
        "Simulation run endpoint is not wired for FMU_BACKEND_MODE=station. "
        "Use FMU_BACKEND_MODE=station in production, or explicitly set "
        "FMU_BACKEND_MODE=local and FMU_LOCAL_DEV_MODE=true for isolated development."
    )