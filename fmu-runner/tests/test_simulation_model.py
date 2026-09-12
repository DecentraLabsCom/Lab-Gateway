from unittest.mock import MagicMock

import pytest

from simulation_model import resolve_fmi_type


def test_resolve_fmi_type_preserves_explicit_request_without_reading_model():
    reader = MagicMock()

    assert resolve_fmi_type("ModelExchange", "/tmp/model.fmu", reader) == "ModelExchange"
    reader.assert_not_called()


@pytest.mark.parametrize(
    "model_description, expected",
    [
        (MagicMock(coSimulation=True, modelExchange=False), "CoSimulation"),
        (MagicMock(coSimulation=False, modelExchange=True), "ModelExchange"),
        (MagicMock(coSimulation=False, modelExchange=False), "CoSimulation"),
    ],
)
def test_resolve_fmi_type_detects_model_description_flags(model_description, expected):
    reader = MagicMock(return_value=model_description)

    assert resolve_fmi_type(None, "/tmp/model.fmu", reader) == expected
    reader.assert_called_once_with("/tmp/model.fmu")


def test_resolve_fmi_type_falls_back_to_cosimulation_when_reading_fails():
    reader = MagicMock(side_effect=RuntimeError("invalid model description"))

    assert resolve_fmi_type(None, "/tmp/model.fmu", reader) == "CoSimulation"
