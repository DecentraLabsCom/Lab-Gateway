import re

import pytest

from simulation_options import (
    SimulationOptionsError,
    parse_simulation_options,
)


def test_parse_simulation_options_preserves_defaults():
    parsed = parse_simulation_options(
        {},
        max_timeout=300,
        max_stop_time=86400,
        min_step_size=1e-6,
        effective_timeout_seconds=lambda requested: requested,
    )

    assert parsed.start_time == 0.0
    assert parsed.stop_time == 10.0
    assert parsed.step_size == 0.01
    assert parsed.timeout == 300
    assert parsed.fmi_type is None
    assert parsed.solver_name == "Euler"


def test_parse_simulation_options_preserves_custom_values_and_timeout_policy():
    seen = []
    parsed = parse_simulation_options(
        {
            "startTime": 1,
            "stopTime": 5,
            "stepSize": 0.1,
            "timeout": 120,
            "fmiType": "ModelExchange",
            "solver": "CVode",
        },
        max_timeout=300,
        max_stop_time=86400,
        min_step_size=1e-6,
        effective_timeout_seconds=lambda requested: seen.append(requested) or 45,
    )

    assert seen == [120]
    assert parsed.timeout == 45
    assert parsed.fmi_type == "ModelExchange"
    assert parsed.solver_name == "CVode"


@pytest.mark.parametrize(
    "options, message",
    [
        ({"startTime": 5, "stopTime": 5}, "stopTime must be greater than startTime"),
        ({"stepSize": 0}, "stepSize must be positive"),
        ({"timeout": 0}, "timeout must be positive"),
        ({"stopTime": 86401}, "stopTime exceeds maximum (86400s)"),
        ({"stepSize": 0.0000001}, "stepSize below minimum (1e-06s)"),
    ],
)
def test_parse_simulation_options_preserves_validation_errors(options, message):
    with pytest.raises(SimulationOptionsError, match=re.escape(message)):
        parse_simulation_options(
            options,
            max_timeout=300,
            max_stop_time=86400,
            min_step_size=1e-6,
            effective_timeout_seconds=lambda requested: requested,
        )


def test_parse_simulation_options_calls_timeout_policy_before_upper_bounds():
    seen = []

    with pytest.raises(SimulationOptionsError, match=re.escape("stopTime exceeds maximum")):
        parse_simulation_options(
            {"stopTime": 86401},
            max_timeout=300,
            max_stop_time=86400,
            min_step_size=1e-6,
            effective_timeout_seconds=lambda requested: seen.append(requested) or requested,
        )

    assert seen == [300]
