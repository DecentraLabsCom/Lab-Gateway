from types import SimpleNamespace

from metadata import _model_metadata_from_model_description, _public_model_metadata


def test_model_metadata_normalizes_defaults_capabilities_and_dimensions():
    dimension = SimpleNamespace(start=4, valueReference=None, variable=None)
    variable = SimpleNamespace(
        name="temperature",
        causality="output",
        type="Real",
        variability="continuous",
        valueReference=7,
        initial="exact",
        unit="K",
        start=293.15,
        min=0.0,
        max=500.0,
        description="Measured temperature",
        quantity="temperature",
        displayUnit="K",
        nominal=293.15,
        declaredType=None,
        dimensions=[dimension],
    )
    model_description = SimpleNamespace(
        fmiVersion="3.0",
        modelName="ThermalModel",
        guid=None,
        instantiationToken="token-1",
        coSimulation=SimpleNamespace(
            canGetAndSetFMUstate=True,
            canSerializeFMUstate=False,
            canHandleVariableCommunicationStepSize=True,
            providesDirectionalDerivative=False,
            providesAdjointDerivatives=True,
            fixedInternalStepSize=0.01,
        ),
        modelExchange=None,
        defaultExperiment=SimpleNamespace(
            startTime=1,
            stopTime=9,
            stepSize=0.5,
            tolerance=1e-5,
        ),
        modelVariables=[variable],
        unitDefinitions=[],
        description="Thermal FMU",
        author="DecentraLabs",
        version="1.0",
        license="MIT",
        generationTool="Test tool",
    )

    metadata = _model_metadata_from_model_description(model_description)

    assert metadata["modelName"] == "ThermalModel"
    assert metadata["defaultStartTime"] == 1.0
    assert metadata["defaultStopTime"] == 9.0
    assert metadata["defaultStepSize"] == 0.5
    assert metadata["defaultTolerance"] == 1e-5
    assert metadata["capabilities"]["canGetAndSetFMUstate"] is True
    assert metadata["capabilities"]["fixedInternalStepSize"] == 0.01
    assert metadata["modelVariables"][0]["dimensions"] == [{"start": 4}]


def test_public_model_metadata_exposes_only_describe_contract_fields():
    public_metadata = _public_model_metadata({
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "simulationType": "CoSimulation",
        "supportsCoSimulation": True,
        "supportsModelExchange": False,
        "defaultStartTime": 0,
        "defaultStopTime": 10,
        "defaultStepSize": 0.1,
        "instantiationToken": "private-token",
        "guid": "private-guid",
        "modelVariables": [{
            "name": "output",
            "causality": "output",
            "type": "Float64",
            "variability": "continuous",
            "unit": "K",
            "start": 300,
            "min": 0,
            "max": 500,
            "dimensions": [{"start": 2}],
            "description": "internal description",
        }],
    })

    assert public_metadata == {
        "fmiVersion": "3.0",
        "simulationKind": "coSimulation",
        "simulationType": "CoSimulation",
        "supportsCoSimulation": True,
        "supportsModelExchange": False,
        "defaultStartTime": 0.0,
        "defaultStopTime": 10.0,
        "defaultStepSize": 0.1,
        "instantiationToken": "private-token",
        "modelVariables": [{
            "name": "output",
            "causality": "output",
            "type": "Float64",
            "variability": "continuous",
            "unit": "K",
            "start": 300,
            "min": 0,
            "max": 500,
            "dimensions": [{"start": 2}],
        }],
    }