"""
Tests for AAS generator and sync endpoint.

Tests the pure generation logic (no BaSyx needed) and the /aas-admin/fmu/{accessKey}/sync
endpoint with mocked BaSyx and FMU reading.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# ── Pure generator tests ─────────────────────────────────────────────

from aas_generator import (
    _aas_id_for_lab,
    _submodel_id_for_fmu,
    _encode_id,
    _fmi_type_to_idta,
    _causality_to_port_type,
    build_simulation_ports,
    build_simulation_submodel,
    build_aas_shell,
)


class TestAasIdGeneration:
    def test_aas_id_format(self):
        assert _aas_id_for_lab("42") == "urn:decentralabs:lab:42"

    def test_submodel_id_format(self):
        assert _submodel_id_for_fmu("42") == "urn:decentralabs:lab:42:sm:simulationModels"

    def test_encode_id_roundtrip(self):
        raw = "urn:decentralabs:lab:42"
        encoded = _encode_id(raw)
        assert isinstance(encoded, str)
        assert "=" not in encoded
        # Must be valid base64url
        import base64
        decoded = base64.urlsafe_b64decode(encoded + "==").decode()
        assert decoded == raw


class TestTypeMapping:
    @pytest.mark.parametrize("fmi,expected", [
        ("Real", "Real"),
        ("Float64", "Real"),
        ("Integer", "Integer"),
        ("Int32", "Integer"),
        ("Boolean", "Boolean"),
        ("String", "String"),
        ("Enumeration", "Enumeration"),
        ("SomethingElse", "Real"),
    ])
    def test_fmi_type_mapping(self, fmi, expected):
        assert _fmi_type_to_idta(fmi) == expected

    @pytest.mark.parametrize("causality,expected", [
        ("input", "Input"),
        ("output", "Output"),
        ("parameter", "Parameter"),
        ("calculatedParameter", "Parameter"),
        ("local", "Internal"),
        ("independent", "Internal"),
        ("unknown", "Internal"),
    ])
    def test_causality_mapping(self, causality, expected):
        assert _causality_to_port_type(causality) == expected


class TestBuildSimulationPorts:
    def test_filters_local_variables(self):
        variables = [
            {"name": "x", "causality": "local", "type": "Real"},
            {"name": "y", "causality": "independent", "type": "Real"},
        ]
        ports = build_simulation_ports(variables)
        assert len(ports) == 0

    def test_creates_input_port(self):
        variables = [
            {"name": "force", "causality": "input", "type": "Real", "unit": "N", "start": 0.0},
        ]
        ports = build_simulation_ports(variables)
        assert len(ports) == 1
        port = ports[0]
        assert port["idShort"] == "force"
        assert port["modelType"] == "SubmodelElementCollection"
        values = {el["idShort"]: el for el in port["value"]}
        assert values["PortDirection"]["value"] == "Input"
        assert values["PortDataType"]["value"] == "Real"
        assert "Unit" in values
        assert values["Unit"]["value"] == "N"
        assert "DefaultValue" in values

    def test_output_port_without_optional_fields(self):
        variables = [
            {"name": "velocity", "causality": "output", "type": "Float64", "variability": "continuous"},
        ]
        ports = build_simulation_ports(variables)
        port = ports[0]
        values = {el["idShort"]: el for el in port["value"]}
        assert values["PortDirection"]["value"] == "Output"
        assert values["PortDataType"]["value"] == "Real"
        assert "Unit" not in values
        assert "DefaultValue" not in values


SAMPLE_METADATA = {
    "modelName": "TestModel",
    "fmiVersion": "3.0",
    "simulationType": "CoSimulation",
    "supportsCoSimulation": True,
    "supportsModelExchange": False,
    "defaultStartTime": 0.0,
    "defaultStopTime": 10.0,
    "defaultStepSize": 0.001,
    "modelVariables": [
        {"name": "force", "causality": "input", "type": "Real", "variability": "continuous", "unit": "N", "start": 0.0},
        {"name": "velocity", "causality": "output", "type": "Real", "variability": "continuous"},
        {"name": "internalState", "causality": "local", "type": "Real", "variability": "continuous"},
    ],
}


class TestBuildSimulationSubmodel:
    def test_submodel_structure(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        assert sm["id"] == "urn:decentralabs:lab:42:sm:simulationModels"
        assert sm["idShort"] == "SimulationModels"
        assert sm["modelType"] == "Submodel"
        assert "semanticId" in sm

    def test_submodel_has_simulation_model_collection(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        elements = sm["submodelElements"]
        assert len(elements) == 1
        sim_model = elements[0]
        assert sim_model["idShort"] == "SimulationModel"
        assert sim_model["modelType"] == "SubmodelElementCollection"

    def test_simulation_model_properties(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        sim_model = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in sim_model["value"]}
        assert props["ModelName"]["value"] == "TestModel"
        assert props["FmiVersion"]["value"] == "3.0"
        assert props["SimulationType"]["value"] == "CoSimulation"
        assert props["SupportsCoSimulation"]["value"] == "true"
        assert props["SupportsModelExchange"]["value"] == "false"
        assert props["DefaultStartTime"]["value"] == "0.0"
        assert props["DefaultStopTime"]["value"] == "10.0"
        assert props["DefaultStepSize"]["value"] == "0.001"
        assert props["AccessKey"]["value"] == "test.fmu"
        assert "SyncTimestamp" in props

    def test_ports_included_for_io_variables(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        sim_model = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in sim_model["value"]}
        assert "Ports" in props
        ports_coll = props["Ports"]
        # Only input + output, not local
        assert len(ports_coll["value"]) == 2
        port_names = {p["idShort"] for p in ports_coll["value"]}
        assert port_names == {"force", "velocity"}

    def test_no_ports_when_only_locals(self):
        metadata = {**SAMPLE_METADATA, "modelVariables": [
            {"name": "x", "causality": "local", "type": "Real"},
        ]}
        sm = build_simulation_submodel("42", "test.fmu", metadata)
        sim_model = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in sim_model["value"]}
        assert "Ports" not in props


class TestBuildAasShell:
    def test_shell_structure(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA)
        assert shell["id"] == "urn:decentralabs:lab:42"
        assert shell["modelType"] == "AssetAdministrationShell"
        assert shell["assetInformation"]["assetKind"] == "Instance"
        assert shell["assetInformation"]["globalAssetId"] == "urn:decentralabs:lab:42"
        assert shell["assetInformation"]["assetType"] == "FMU"

    def test_shell_references_submodel(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA)
        refs = shell["submodels"]
        assert len(refs) == 1
        assert refs[0]["keys"][0]["value"] == "urn:decentralabs:lab:42:sm:simulationModels"

    def test_shell_idshort_format(self):
        shell = build_aas_shell("7", "motor.fmu", SAMPLE_METADATA)
        assert shell["idShort"] == "DecentraLabs_Lab_7"


# ── Endpoint integration tests ───────────────────────────────────────

from fastapi.testclient import TestClient


def _get_app():
    """Import app lazily to avoid polluting module-level state for other test files."""
    with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": 1, "accessKey": "test.fmu"}):
        from main import app
    return app


class TestAasSyncEndpoint:
    """Test POST /aas-admin/fmu/{accessKey}/sync with mocked FMU + BaSyx."""

    def _mock_model_description(self):
        """Create a minimal mock that _model_metadata_from_model_description can process."""
        md = MagicMock()
        md.fmiVersion = "2.0"
        md.modelName = "MockModel"
        md.guid = "mock-guid-123"
        md.instantiationToken = None

        cs = MagicMock()
        md.coSimulation = cs
        md.modelExchange = None

        exp = MagicMock()
        exp.startTime = "0.0"
        exp.stopTime = "1.0"
        exp.stepSize = "0.01"
        md.defaultExperiment = exp

        var1 = MagicMock()
        var1.name = "input1"
        var1.causality = "input"
        var1.type = "Real"
        var1.variability = "continuous"
        var1.valueReference = 1
        var1.initial = None
        var1.unit = "m/s"
        var1.start = 0.0
        var1.min = None
        var1.max = None
        var1.declaredType = None
        md.modelVariables = [var1]

        return md

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("main.read_model_description")
    @patch("main._resolve_fmu_path")
    def test_sync_success(self, mock_resolve, mock_read_md, mock_sync):
        mock_resolve.return_value = "/fake/path/test.fmu"
        mock_read_md.return_value = self._mock_model_description()
        mock_sync.return_value = {
            "aasId": "urn:decentralabs:lab:test.fmu",
            "submodelId": "urn:decentralabs:lab:test.fmu:sm:simulationModels",
            "created": True,
            "updated": False,
            "synced": True,
        }

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/test.fmu/sync")
        assert resp.status_code == 200
        body = resp.json()
        assert body["synced"] is True
        assert body["aasId"] == "urn:decentralabs:lab:test.fmu"

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("main.read_model_description")
    @patch("main._resolve_fmu_path")
    def test_sync_with_lab_id_param(self, mock_resolve, mock_read_md, mock_sync):
        mock_resolve.return_value = "/fake/path/motor.fmu"
        mock_read_md.return_value = self._mock_model_description()
        mock_sync.return_value = {
            "aasId": "urn:decentralabs:lab:99",
            "submodelId": "urn:decentralabs:lab:99:sm:simulationModels",
            "created": True,
            "synced": True,
        }

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/motor.fmu/sync?labId=99")
        assert resp.status_code == 200
        # Verify the lab_id passed to sync_fmu_to_basyx was "99", not "motor.fmu"
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        assert call_kwargs.kwargs.get("lab_id") or call_kwargs[1].get("lab_id") or call_kwargs[0][0] == "99"

    @patch("main.read_model_description")
    @patch("main._resolve_fmu_path")
    def test_sync_fmu_not_found(self, mock_resolve, mock_read_md):
        from fastapi import HTTPException as _H
        mock_resolve.side_effect = _H(status_code=404, detail="FMU file not found: nonexistent.fmu")

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/nonexistent.fmu/sync")
        assert resp.status_code == 404

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("main.read_model_description")
    @patch("main._resolve_fmu_path")
    def test_sync_basyx_error(self, mock_resolve, mock_read_md, mock_sync):
        mock_resolve.return_value = "/fake/path/test.fmu"
        mock_read_md.return_value = self._mock_model_description()
        mock_sync.return_value = {"error": "submodel creation failed: 500"}

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/test.fmu/sync")
        assert resp.status_code == 502
        assert "submodel creation failed" in resp.json()["detail"]
