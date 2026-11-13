from fastapi import HTTPException
import pytest

from fmu_model_normalization import normalize_model_metadata


def test_cosimulation_model_structure_is_preserved_after_variables_are_normalized():
    metadata = normalize_model_metadata({
        "modelName": "CoSimulationStructure",
        "fmiVersion": "2.0",
        "simulationKind": "coSimulation",
        "simulationType": "CoSimulation",
        "supportsModelExchange": False,
        "supportsCoSimulation": True,
        "modelVariables": [
            {"name": "drive_input", "valueReference": 1, "type": "Real", "causality": "input"},
            {"name": "shaft_position", "valueReference": 2, "type": "Real", "causality": "output"},
        ],
        "modelStructure": {
            "outputs": [{
                "name": "shaft_position",
                "valueReference": 2,
                "dependencies": [1],
                "dependencyNames": ["drive_input"],
                "dependenciesKind": ["dependent"],
            }],
        },
    })

    assert metadata["modelStructure"]["outputs"] == [{
        "valueReference": 2,
        "name": "shaft_position",
        "dependencies": [1],
        "dependencyNames": ["drive_input"],
        "dependenciesKind": ["dependent"],
    }]


def test_model_exchange_model_structure_is_validated_after_variables_are_normalized():
    metadata = normalize_model_metadata({
        "modelName": "StateSpace",
        "fmiVersion": "2.0",
        "simulationKind": "modelExchange",
        "simulationType": "ModelExchange",
        "supportsModelExchange": True,
        "supportsCoSimulation": False,
        "modelVariables": [
            {"name": "x", "valueReference": 1, "type": "Real", "causality": "local"},
            {"name": "der_x", "valueReference": 2, "type": "Real", "causality": "local"},
            {"name": "y", "valueReference": 3, "type": "Real", "causality": "output"},
        ],
        "modelStructure": {
            "outputs": [{"valueReference": 3}],
            "derivatives": [{"valueReference": 2, "stateValueReference": 1}],
            "initialUnknowns": [{"valueReference": 1}],
        },
    })

    assert [item["valueReference"] for item in metadata["modelStructure"]["outputs"]] == [3]
    assert metadata["modelStructure"]["derivatives"] == [
        {"valueReference": 2, "stateValueReference": 1},
    ]


def test_model_exchange_model_structure_still_rejects_unknown_references():
    with pytest.raises(HTTPException, match="invalid FMI ModelStructure"):
        normalize_model_metadata({
            "fmiVersion": "2.0",
            "simulationKind": "modelExchange",
            "simulationType": "ModelExchange",
            "supportsModelExchange": True,
            "modelVariables": [
                {"name": "x", "valueReference": 1, "type": "Real", "causality": "local"},
            ],
            "modelStructure": {"derivatives": [{"valueReference": 99}]},
        })
