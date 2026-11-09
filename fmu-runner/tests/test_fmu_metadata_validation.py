"""Preserve safe FMI declarations at the untrusted Station boundary."""

from copy import deepcopy

from fastapi import HTTPException
import pytest

from fmu_model_normalization import normalize_model_metadata, normalize_variable


def test_variable_keeps_clock_alias_array_and_declared_type_information():
    variable = normalize_variable({
        "name": "tick", "type": "Clock", "causality": "input",
        "intervalVariability": "tunable", "canBeDeactivated": True,
        "supportsFraction": False, "intervalDecimal": "0.25", "shiftDecimal": 0,
        "resolution": "100", "intervalCounter": 25, "shiftCounter": 0, "priority": 2,
        "alias": "alias", "aliasOf": " reference ", "initial": " exact ",
        "aliases": [None, {"name": ""}, {"name": " clockAlias ", "description": " alias ", "displayUnit": " s "}],
        "relativeQuantity": True, "unbounded": False, "reinit": False,
        "maxSize": "16", "nominal": "2", "description": " Clock ",
        "displayName": " Periodic clock ", "quantity": " time ", "unit": "s",
        "displayUnit": {"name": " ms ", "factor": 1000, "offset": 0},
        "dimensions": [None, {}, {"start": "3", "valueReference": "7", "variableName": " count "}],
        "clocks": [True, -1, "not-a-reference", "0", 7],
        "declaredType": {
            "name": " SampleClock ", "type": " Clock ", "description": " periodic ",
            "unit": " s ", "quantity": " time ", "displayUnit": " ms ",
            "mimeType": " application/octet-stream ", "intervalVariability": " tunable ",
            "min": "0", "max": 100, "nominal": "1", "maxSize": 32,
            "relativeQuantity": True, "unbounded": False,
            "supportsFraction": True, "canBeDeactivated": False,
            "intervalDecimal": "0.25", "shiftDecimal": 0,
            "resolution": 100, "intervalCounter": 25, "shiftCounter": 0, "priority": 0,
            "items": [None, {"name": ""}, {"name": "bad", "value": True},
                      {"name": " high ", "value": 2**60, "description": " large integer "}],
        },
    }, 9)

    assert variable["valueReference"] == 9
    assert variable["intervalDecimal"] == 0.25
    assert variable["supportsFraction"] is False
    assert variable["clocks"] == [0, 7]
    assert variable["aliasOf"] == "reference"
    assert variable["aliases"] == [{"name": "clockAlias", "description": "alias", "displayUnit": "s"}]
    assert variable["dimensions"] == [{"start": 3, "valueReference": 7, "variableName": "count"}]
    assert variable["displayUnit"] == {"name": "ms", "factor": 1000.0, "offset": 0.0}
    assert variable["declaredType"]["items"] == [{"name": "high", "value": str(2**60), "description": "large integer"}]
    assert variable["declaredType"]["shiftCounter"] == 0
    assert variable["initial"] == "exact"


@pytest.mark.parametrize("bad", [True, "bad", {}, float("nan"), float("inf")])
def test_malformed_optional_numeric_metadata_is_not_forwarded(bad):
    value = normalize_variable({
        "name": "clock", "type": "Clock", "intervalDecimal": bad, "shiftDecimal": bad,
        "resolution": bad, "intervalCounter": bad, "shiftCounter": bad,
        "priority": bad, "nominal": bad, "maxSize": bad,
        "declaredType": {"name": "ClockType", "nominal": bad, "maxSize": bad,
                         "intervalDecimal": bad, "shiftDecimal": bad, "resolution": bad},
    }, 1)
    for key in ("intervalDecimal", "shiftDecimal", "resolution", "intervalCounter", "shiftCounter", "priority", "nominal", "maxSize"):
        assert key not in value
    assert value["declaredType"] == {"name": "ClockType"}


@pytest.mark.parametrize("unit", [
    {"name": "k", "factor": 0}, {"name": "k", "factor": "bad"},
    {"name": "k", "offset": float("inf")}, {"name": "k", "inverse": True, "offset": 1},
    {"name": " "},
])
def test_invalid_display_unit_conversions_are_omitted(unit):
    result = normalize_variable({"name": "x", "displayUnit": unit}, 1)
    assert "displayUnit" not in result


def test_enumeration_values_remain_lossless_and_invalid_items_are_filtered():
    result = normalize_variable({
        "name": "mode", "type": "Enumeration", "valueReference": 0,
        "min": "-9007199254740993", "max": "9007199254740993",
        "displayUnit": " count ", "mimeType": " text/plain ", "start": "ready",
        "enumItems": [None, {"name": 3, "value": 1}, {"name": "bad", "value": "1.5"},
                      {"name": "small", "value": "-2", "description": " small "},
                      {"name": "large", "value": str(2**60)}, {"name": "", "value": 1}],
    }, 1)
    assert result["valueReference"] == 0
    assert result["min"] == -9007199254740993
    assert result["max"] == 9007199254740993
    assert result["enumItems"] == [
        {"name": "small", "value": -2, "description": "small"},
        {"name": "large", "value": str(2**60)},
    ]
    assert result["mimeType"] == "text/plain"


def test_model_normalizes_units_type_definitions_capabilities_and_provenance():
    model = normalize_model_metadata({
        "variables": [{"name": "x", "type": "Float64"}], "guid": 123,
        "simulationType": "ModelExchange", "supportsModelExchange": True,
        "modelExchangeCapabilities": {"needsCompletedIntegratorStep": False},
        "numberOfContinuousStates": 1, "numberOfEventIndicators": 0,
        "description": " model ", "author": " provider ", "version": " 1 ",
        "copyright": " copyright ", "license": " MIT ", "generationTool": " exporter ",
        "generationDateAndTime": " 2026-01-01T00:00:00Z ", "variableNamingConvention": "structured",
        "defaultTolerance": "0.0001", "defaultStartTime": "0", "defaultStopTime": 10,
        "defaultStepSize": "0.1", "capabilities": {"canGetAndSetFMUstate": True,
            "maxOutputDerivativeOrder": 2, "recommendedIntermediateInputSmoothness": 0,
            "fixedInternalStepSize": "0.1", "unknown": "not exposed"},
        "unitDefinitions": [None, {}, {"name": " dimensionless ", "baseUnit": {}},
            {"name": " K ", "baseUnit": {"K": 1, "kg": True, "factor": 2, "offset": -273.15},
             "displayUnits": [None, {}, {"name": "bad", "factor": 0},
                              {"name": "C", "offset": -273.15},
                              {"name": "reciprocal", "factor": 2, "inverse": True}]}],
        "typeDefinitions": [None, {}, {"name": " Mode ", "type": " Enumeration ",
            "description": " states ", "min": "-2", "max": 3, "nominal": "1",
            "relativeQuantity": False, "unbounded": True, "supportsFraction": False,
            "canBeDeactivated": True, "resolution": "100", "intervalCounter": 1,
            "shiftCounter": 0, "priority": 0, "maxSize": 10,
            "intervalDecimal": "0.1", "shiftDecimal": 0,
            "items": [None, {"name": "bad", "value": True}, {"name": "bad", "value": "1.2"},
                      {"name": "zero", "value": 0.0, "description": " zero "},
                      {"name": "huge", "value": str(2**60)}]}],
    })
    assert model["executionInterface"] == "ModelExchange"
    assert model["availableExecutionInterfaces"] == ["ModelExchange"]
    assert model["guid"] == "123"
    assert model["author"] == "provider"
    assert model["defaultTolerance"] == 0.0001
    assert model["unitDefinitions"][0] == {"name": "dimensionless", "baseUnit": {}}
    unit = model["unitDefinitions"][1]
    assert unit["baseUnit"] == {"K": 1, "factor": 2.0, "offset": -273.15}
    assert unit["displayUnits"] == [{"name": "C", "offset": -273.15}, {"name": "reciprocal", "factor": 2.0, "inverse": True}]
    assert model["typeDefinitions"][0]["items"] == [
        {"name": "zero", "value": "0", "description": "zero"}, {"name": "huge", "value": str(2**60)},
    ]
    assert model["capabilities"] == {"canGetAndSetFMUstate": True, "maxOutputDerivativeOrder": 2,
                                    "recommendedIntermediateInputSmoothness": 0, "fixedInternalStepSize": 0.1}


@pytest.mark.parametrize("extra", [
    {"modelVariables": "not a list"}, {"modelVariables": [None]},
    {"availableExecutionInterfaces": "CoSimulation"},
    {"availableExecutionInterfaces": ["ScheduledExecution"]},
    {"availableExecutionInterfaces": ["CoSimulation", "CoSimulation"]},
    {"availableExecutionInterfaces": ["ModelExchange"], "supportsModelExchange": False},
    {"supportsModelExchange": True, "modelExchangeCapabilities": []},
    {"supportsModelExchange": True, "modelExchangeCapabilities": {"unknown": True}},
    {"supportsModelExchange": True, "modelExchangeCapabilities": {"needsExecutionTool": "false"}},
    {"fmiLsDae": {}},
])
def test_station_contract_rejects_inconsistent_shapes_and_interfaces(extra):
    with pytest.raises(HTTPException) as error:
        normalize_model_metadata({"modelVariables": [], "supportsCoSimulation": True, **extra})
    assert error.value.status_code == 502


def _dae_model():
    return {
        "fmiVersion": "3.0", "supportsFmiLsDae": True, "supportsCoSimulation": True,
        "modelVariables": [
            {"name": "enableDAE", "valueReference": 1, "causality": "structuralParameter", "variability": "fixed", "type": "Boolean"},
            {"name": "x", "valueReference": 2, "type": "Float64"},
            {"name": "residual", "valueReference": 3, "type": "Float64"},
        ],
        "fmiLsDae": {
            "manifestName": "org.fmi-standard.fmi-ls-dae", "manifestVersion": "1.0.0-alpha.1",
            "enableDAEParameter": "enableDAE", "algebraicVariables": ["x"],
            "algebraicValueReferences": [2], "residualVariableCount": 1,
            "residualVariables": [{"name": "residual", "type": "Float64", "valueReference": 3}],
            "modelStructure": [{"kind": "Residual", "valueReference": 3, "dependencies": [2],
                                "dependencyNames": ["x"], "dependenciesKind": ["dependent"]}],
        },
    }


def test_dae_metadata_keeps_selector_dependencies_and_residual_mapping():
    result = normalize_model_metadata(_dae_model())
    assert result["fmiLsDae"]["algebraicValueReferences"] == [2]
    assert result["fmiLsDae"]["modelStructure"]["residuals"] == [{
        "valueReference": 3, "dependencies": [2], "dependencyNames": ["x"], "dependenciesKind": ["dependent"],
    }]


@pytest.mark.parametrize("field,value", [
    ("manifestName", "other"), ("manifestVersion", "2"), ("enableDAEParameter", "unknown"),
    ("algebraicVariables", ["x", "x"]), ("algebraicVariables", [None]),
    ("algebraicValueReferences", [2, 2]), ("algebraicValueReferences", [True]),
    ("residualVariableCount", True), ("residualVariableCount", -1),
    ("residualVariables", []), ("residualVariables", [None]),
    ("residualVariables", [{"name": "r", "type": "Boolean", "valueReference": 3}]),
    ("modelStructure", [None]), ("modelStructure", [{"kind": "unknown", "valueReference": 3}]),
    ("modelStructure", [{"kind": "Residual", "valueReference": 99}]),
])
def test_dae_metadata_rejects_invalid_or_inconsistent_manifests(field, value):
    payload = deepcopy(_dae_model())
    payload["fmiLsDae"][field] = value
    with pytest.raises(HTTPException) as error:
        normalize_model_metadata(payload)
    assert error.value.status_code == 502
