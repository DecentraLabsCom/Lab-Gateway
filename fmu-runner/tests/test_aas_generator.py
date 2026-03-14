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


class TestExtraInfoFields:
    """Tests for optional extra_info fields in build_* functions and sync endpoint."""

    # -- build_simulation_submodel extra_info --

    def test_submodel_extra_info_license(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"license": "MIT"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "License" in props
        assert props["License"]["value"] == "MIT"

    def test_submodel_extra_info_documentation_url(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"documentationUrl": "https://example.com"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "DocumentationUrl" in props
        assert props["DocumentationUrl"]["value"] == "https://example.com"

    def test_submodel_extra_info_contact_email(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"contactEmail": "lab@example.com"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "ContactEmail" in props
        assert props["ContactEmail"]["value"] == "lab@example.com"

    def test_submodel_extra_info_empty_fields_not_included(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"license": "", "documentationUrl": "  "})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "License" not in props
        assert "DocumentationUrl" not in props

    def test_submodel_extra_info_none_is_noop(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, None)
        # No extra properties should be present
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "License" not in props
        assert "DocumentationUrl" not in props
        assert "ContactEmail" not in props

    # -- build_aas_shell extra_info --

    def test_shell_description_added(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA, {"description": "My FMU model"})
        assert "description" in shell
        assert shell["description"][0]["language"] == "en"
        assert shell["description"][0]["text"] == "My FMU model"

    def test_shell_description_empty_not_added(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA, {"description": "  "})
        assert "description" not in shell

    def test_shell_extra_info_none_no_description(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA, None)
        assert "description" not in shell


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

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("main.read_model_description")
    @patch("main._resolve_fmu_path")
    def test_sync_extra_info_passed_via_query(self, mock_resolve, mock_read_md, mock_sync):
        mock_resolve.return_value = "/fake/path/test.fmu"
        mock_read_md.return_value = self._mock_model_description()
        mock_sync.return_value = {"aasId": "urn:decentralabs:lab:1", "created": True}

        client = TestClient(_get_app())
        resp = client.post(
            "/aas-admin/fmu/test.fmu/sync?license=MIT&documentationUrl=https%3A%2F%2Fdocs.example.com&contactEmail=lab%40example.com&description=My+FMU"
        )
        assert resp.status_code == 200
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args
        extra = call_kwargs.kwargs.get("extra_info") or (call_kwargs[1].get("extra_info") if len(call_kwargs) > 1 else None)
        assert extra is not None
        assert extra.get("license") == "MIT"
        assert extra.get("documentationUrl") == "https://docs.example.com"
        assert extra.get("contactEmail") == "lab@example.com"
        assert extra.get("description") == "My FMU"


# ── sync_fmu_to_basyx unit tests (disabled / unreachable) ────────────

import pytest
import httpx
import aas_generator as _aas_mod


class TestSyncFmuToBasyxDegradation:
    """Tests for graceful degradation when BaSyx is not available."""

    @pytest.mark.asyncio
    async def test_disabled_when_no_url(self):
        """If BASYX_AAS_URL is empty, sync returns disabled=True without hitting network."""
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = ""
        try:
            result = await _aas_mod.sync_fmu_to_basyx("42", "motor.fmu", SAMPLE_METADATA)
            assert result.get("disabled") is True
            assert result.get("synced") is None
            assert "error" not in result
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_error_when_basyx_unreachable(self):
        """If BaSyx host is unreachable, sync returns an error dict instead of raising."""
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "http://127.0.0.1:19999"  # nothing listening here
        try:
            result = await _aas_mod.sync_fmu_to_basyx("42", "motor.fmu", SAMPLE_METADATA)
            assert "error" in result
            assert "BaSyx unreachable" in result["error"]
            assert result.get("synced") is None
        finally:
            _aas_mod.BASYX_AAS_URL = original


# ── _parse_aasx unit tests ──────────────────────────────────────────

import io
import json
import zipfile

import aas_generator as _aas_mod


def _make_aasx(shells=None, submodels=None, concept_descs=None, bad_zip=False) -> bytes:
    """Build a minimal in-memory AASX package for testing."""
    if bad_zip:
        return b"not a zip"

    env = {}
    if shells is not None:
        env["assetAdministrationShells"] = shells
    if submodels is not None:
        env["submodels"] = submodels
    if concept_descs is not None:
        env["conceptDescriptions"] = concept_descs

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Write _rels/.rels pointing to the origin part
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin"'
            ' Target="/aasx/data.json" Id="r1"/>'
            "</Relationships>"
        )
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("aasx/data.json", json.dumps(env))
    return buf.getvalue()


class TestParseAasx:
    """Unit tests for the _parse_aasx() helper."""

    def test_parse_shells_and_submodels(self):
        shell = {"id": "urn:test:shell:1", "idShort": "testShell"}
        submodel = {"id": "urn:test:sm:1", "idShort": "testSm"}
        pkg = _make_aasx(shells=[shell], submodels=[submodel])
        result = _aas_mod._parse_aasx(pkg)
        assert result["shells"] == [shell]
        assert result["submodels"] == [submodel]

    def test_parse_empty_package(self):
        pkg = _make_aasx(shells=[], submodels=[])
        result = _aas_mod._parse_aasx(pkg)
        assert result["shells"] == []
        assert result["submodels"] == []

    def test_bad_zip_returns_empty(self):
        result = _aas_mod._parse_aasx(b"not a zip")
        assert result["shells"] == []
        assert result["submodels"] == []

    def test_fallback_scan_without_rels(self):
        """If _rels/.rels is absent, should still find JSON via filesystem scan."""
        env = {"assetAdministrationShells": [{"id": "urn:scan:1"}], "submodels": []}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("aasx/data.json", json.dumps(env))
        result = _aas_mod._parse_aasx(buf.getvalue())
        assert result["shells"] == [{"id": "urn:scan:1"}]


class TestSyncFmuToBasyxAasx:
    """Tests for the aasx_bytes path in sync_fmu_to_basyx()."""

    @pytest.mark.asyncio
    async def test_aasx_disabled_when_no_url(self):
        """aasx_bytes path still returns disabled when BASYX_AAS_URL is empty."""
        pkg = _make_aasx(shells=[{"id": "urn:s:1"}], submodels=[{"id": "urn:sm:1"}])
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = ""
        try:
            result = await _aas_mod.sync_fmu_to_basyx("42", "x.fmu", {}, aasx_bytes=pkg)
            assert result.get("disabled") is True
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_aasx_parse_empty_returns_error(self):
        """Empty AASX (no shells, no submodels) returns an error without uploading anything."""
        pkg = _make_aasx(shells=[], submodels=[])
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "http://basyx-test:8081"
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            mock_client = AsyncMock()
            mock_client.put = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await _aas_mod.sync_fmu_to_basyx("42", "x.fmu", {}, aasx_bytes=pkg)

            # Should return an error without calling PUT/POST
            assert "error" in result
            assert "no shells or submodels" in result["error"]
            mock_client.put.assert_not_called()
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_aasx_upload_success(self):
        """Happy path: shells + submodels from AASX are PUT to BaSyx successfully."""
        shell = {"id": "urn:test:shell:1", "idShort": "s1"}
        submodel = {"id": "urn:test:sm:1", "idShort": "sm1"}
        pkg = _make_aasx(shells=[shell], submodels=[submodel])

        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "http://basyx-test:8081"
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 201

            mock_client = AsyncMock()
            mock_client.put = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await _aas_mod.sync_fmu_to_basyx("42", "x.fmu", {}, aasx_bytes=pkg)

            assert result.get("aasxUpload") is True
            assert result.get("synced") is True
            assert result["uploadedAasIds"] == ["urn:test:shell:1"]
            assert result["uploadedSubmodelIds"] == ["urn:test:sm:1"]
            assert result["created"] is True
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_aasx_upload_uses_aasx_ids_not_lab_ids(self):
        """The returned aasId/submodelId should come from the AASX, not lab_id computation."""
        shell = {"id": "urn:custom:shell:xyz"}
        submodel = {"id": "urn:custom:sm:xyz"}
        pkg = _make_aasx(shells=[shell], submodels=[submodel])

        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "http://basyx-test:8081"
        try:
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            mock_client = AsyncMock()
            mock_client.put = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await _aas_mod.sync_fmu_to_basyx("lab42", "x.fmu", {}, aasx_bytes=pkg)

            assert result["aasId"] == "urn:custom:shell:xyz"
            assert result["submodelId"] == "urn:custom:sm:xyz"
        finally:
            _aas_mod.BASYX_AAS_URL = original


class TestAasSyncEndpointMultipart:
    """Test POST /aas-admin/fmu/{accessKey}/sync with multipart AASX upload."""

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    def test_sync_with_aasx_file(self, mock_sync):
        pkg = _make_aasx(shells=[{"id": "urn:s:1"}], submodels=[{"id": "urn:sm:1"}])
        mock_sync.return_value = {
            "aasId": "urn:s:1",
            "submodelId": "urn:sm:1",
            "created": True,
            "aasxUpload": True,
            "uploadedAasIds": ["urn:s:1"],
            "uploadedSubmodelIds": ["urn:sm:1"],
            "synced": True,
        }

        from fastapi.testclient import TestClient
        client = TestClient(_get_app())
        resp = client.post(
            "/aas-admin/fmu/test.fmu/sync",
            files={"file": ("package.aasx", pkg, "application/octet-stream")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aasxUpload"] is True
        # sync_fmu_to_basyx should have been called with aasx_bytes, NOT read_model_description
        call_kwargs = mock_sync.call_args.kwargs
        assert call_kwargs.get("aasx_bytes") is not None

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    def test_sync_with_aasx_and_lab_id_form_field(self, mock_sync):
        pkg = _make_aasx(shells=[{"id": "urn:s:99"}], submodels=[])
        mock_sync.return_value = {
            "aasId": "urn:s:99", "submodelId": "urn:sm:99",
            "created": True, "aasxUpload": True,
            "uploadedAasIds": ["urn:s:99"], "uploadedSubmodelIds": [],
            "synced": True,
        }

        from fastapi.testclient import TestClient
        client = TestClient(_get_app())
        resp = client.post(
            "/aas-admin/fmu/motor.fmu/sync",
            data={"labId": "99"},
            files={"file": ("p.aasx", pkg, "application/octet-stream")},
        )
        assert resp.status_code == 200
        call_kwargs = mock_sync.call_args.kwargs
        assert call_kwargs.get("lab_id") == "99"
