import pytest
from pydantic import ValidationError

from simulation_request import SimulationRequest


def test_simulation_request_preserves_defaults_and_payload_fields():
    request = SimulationRequest(parameters={"mass": 1.5}, options={"stopTime": 2})

    assert request.reservationKey is None
    assert request.labId is None
    assert request.parameters == {"mass": 1.5}
    assert request.options == {"stopTime": 2}


@pytest.mark.parametrize("value, expected", [("42", "42"), (42, "42"), (0, "0")])
def test_simulation_request_normalizes_string_and_integer_lab_ids(value, expected):
    assert SimulationRequest(labId=value).labId == expected


@pytest.mark.parametrize("value", [True, False, 1.5, []])
def test_simulation_request_rejects_non_string_non_integer_lab_ids(value):
    with pytest.raises(ValidationError):
        SimulationRequest(labId=value)


def test_simulation_request_accepts_models_with_more_than_32_fmi_parameters():
    request = SimulationRequest(parameters={f"parameter_{index}": index for index in range(34)})
    assert len(request.parameters) == 34


def test_simulation_request_rejects_excessive_parameter_maps():
    with pytest.raises(ValidationError, match="at most 128 parameters"):
        SimulationRequest(parameters={f"parameter_{index}": index for index in range(129)})


def test_simulation_request_obeys_configured_gateway_parameter_limit(monkeypatch):
    monkeypatch.setattr("simulation_request._MAX_SIMULATION_PARAMETERS", 64)
    request = SimulationRequest(parameters={f"parameter_{index}": index for index in range(64)})
    assert len(request.parameters) == 64
    with pytest.raises(ValidationError, match="at most 64 parameters"):
        SimulationRequest(parameters={f"parameter_{index}": index for index in range(65)})
