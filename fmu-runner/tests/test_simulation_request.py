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
