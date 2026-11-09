"""Provider presets and experiments must never bypass the consumer write policy."""

from copy import deepcopy

import pytest

from catalog_router import filter_authorized_experiments, filter_authorized_parameter_sets


@pytest.fixture
def policy():
    return {
        "variables": {"gain": {"writeAt": ["initialization"]},
                      "u": {"writeAt": ["initialization", "runtime"]},
                      "mode": {"writeAt": ["initialization"]},
                      "locked": {"writeAt": []}},
        "modelVariables": [
            {"name": "gain", "causality": "parameter", "variability": "fixed", "type": "Float64", "unit": "K"},
            {"name": "u", "causality": "input", "type": "Float64"},
            {"name": "mode", "causality": "parameter", "type": "Enumeration",
             "enumItems": [{"name": "off", "value": 0}, {"name": "on", "value": 2}]},
            {"name": "locked", "causality": "output", "type": "Float64"},
        ],
    }


def _preset(**changes):
    return {"id": "preset-1", "name": " Warm ", "description": "Provider preset",
            "parameters": {"gain": 2.5}, "parameterUnits": {"gain": "K"}, **changes}


def test_presets_preserve_units_values_and_enum_meanings_without_mutating_provider_data(policy):
    preset = _preset(parameters={"gain": 2.5, "mode": ["off", "on"], "u": [0, True, "text"]})
    original = deepcopy(preset)
    result = filter_authorized_parameter_sets([None, preset], policy)
    assert result == [{"id": "preset-1", "name": "Warm", "description": "Provider preset",
                       "parameters": {"gain": 2.5, "mode": [0, 2], "u": [0, True, "text"]}}]
    assert preset == original


@pytest.mark.parametrize("changes", [
    {"id": 1}, {"id": "x" * 65}, {"name": " "}, {"name": "x" * 181},
    {"parameters": {}}, {"parameters": []}, {"parameterUnits": []},
    {"parameterUnits": {"gain": "C"}}, {"parameterUnits": {"gain": 2}},
    {"parameters": {"gain": 2, "locked": 5}}, {"parameters": {"missing": 1}},
    {"parameters": {"mode": "missing"}}, {"parameters": {"gain": float("inf")}},
    {"parameters": {"gain": float("nan")}}, {"parameters": {"gain": 2**53}},
    {"parameters": {"gain": "x" * 65537}}, {"parameters": {"gain": [[1]]}},
    {"parameters": {"gain": {"nested": 1}}}, {"parameters": {"gain": [0] * 4097}},
])
def test_incomplete_unauthorized_or_unsafe_presets_are_rejected_as_a_whole(policy, changes):
    assert filter_authorized_parameter_sets([_preset(**changes)], policy) == []


@pytest.mark.parametrize("mutate", [
    lambda p: p["variables"].update(gain=None),
    lambda p: p["variables"].update(gain={"writeAt": "initialization"}),
    lambda p: p["modelVariables"][0].update(variability="constant"),
    lambda p: p["modelVariables"][0].update(causality="output"),
    lambda p: p["modelVariables"].clear(),
])
def test_presets_require_actual_writable_model_variables(policy, mutate):
    mutate(policy)
    assert filter_authorized_parameter_sets([_preset()], policy) == []


def _experiment(**changes):
    return {"name": " Step response ", "status": "ready", "parameters": {"gain": 2},
            "parameterUnits": {"gain": "K"},
            "options": {"startTime": 0, "stopTime": 1, "stepSize": 0.25},
            "inputSchedule": [{"time": 0.25, "values": {"u": 1}}], **changes}


def _discover(experiment):
    return {"resourceSets": [{"description": "Provider experiment", "experiments": [experiment]}]}


def test_experiments_keep_authorized_initialization_and_ordered_grid_aligned_stimuli(policy):
    experiment = _experiment()
    original = deepcopy(experiment)
    assert filter_authorized_experiments(_discover(experiment), policy) == [{
        "id": "experiment-0-0", "name": "Step response", "description": "Provider experiment",
        "parameters": {"gain": 2}, "options": {"startTime": 0.0, "stopTime": 1.0, "stepSize": 0.25},
        "inputSchedule": [{"time": 0.25, "values": {"u": 1.0}}],
    }]
    assert experiment == original


@pytest.mark.parametrize("changes", [
    {"status": "unresolved"}, {"eligibleForSmokeProbe": False}, {"name": " "},
    {"name": "x" * 181}, {"parameters": []}, {"parameterUnits": []}, {"options": []},
    {"inputSchedule": None}, {"inputSchedule": [{}] * 129},
    {"options": {"unsupported": 1}}, {"options": {"stepSize": True}},
    {"options": {"startTime": float("inf")}}, {"options": {"stepSize": 0}},
    {"options": {"startTime": 2, "stopTime": 1}},
    {"parameters": {"locked": 1}}, {"parameters": {}, "parameterUnits": {"gain": "K"}},
    {"parameters": {}, "parameterUnits": {}, "options": {}, "inputSchedule": []},
    {"options": {"stopTime": 1, "stepSize": 0.25}},
])
def test_experiments_cannot_smuggle_invalid_options_or_hidden_parameters(policy, changes):
    assert filter_authorized_experiments(_discover(_experiment(**changes)), policy) == []


@pytest.mark.parametrize("schedule", [
    [None], [{"time": 0.25, "values": {"u": 1}, "extra": True}],
    [{"time": True, "values": {"u": 1}}], [{"time": -0.25, "values": {"u": 1}}],
    [{"time": 1, "values": {"u": 1}}], [{"time": 0.1, "values": {"u": 1}}],
    [{"time": 0.5, "values": {"u": 1}}, {"time": 0.25, "values": {"u": 2}}],
    [{"time": 0.25, "values": {"u": 1}}, {"time": 0.25, "values": {"u": 2}}],
    [{"time": 0.25, "values": {}}], [{"time": 0.25, "values": []}],
    [{"time": 0.25, "values": {"locked": 1}}], [{"time": 0.25, "values": {"gain": 1}}],
    [{"time": 0.25, "values": {"u": True}}], [{"time": 0.25, "values": {"u": float("nan")}}],
])
def test_runtime_schedule_rejects_unauthorized_off_grid_duplicate_and_non_finite_writes(policy, schedule):
    assert filter_authorized_experiments(_discover(_experiment(inputSchedule=schedule)), policy) == []


@pytest.mark.parametrize("invalid", [None, [], {}, {"resourceSets": "bad"}])
def test_malformed_discovery_is_not_published_as_an_executable_experiment(policy, invalid):
    assert filter_authorized_experiments(invalid, policy) == []


def test_provider_catalog_limits_are_bounded_and_bad_entries_do_not_hide_valid_ones(policy):
    assert len(filter_authorized_parameter_sets([_preset()] * 25, policy)) == 24
    discovery = {"resourceSets": [None, {}, {"experiments": [None, _experiment(inputSchedule=[], description="Own description")]}]}
    result = filter_authorized_experiments(discovery, policy)
    assert len(result) == 1
    assert result[0]["id"] == "experiment-2-1"
    assert result[0]["description"] == "Own description"
