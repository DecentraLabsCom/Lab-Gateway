"""
Tests for AAS generator and sync endpoint.

Tests the pure generation logic (no BaSyx needed) and the /aas-admin/fmu/{accessKey}/sync
endpoint with mocked BaSyx and FMU reading.
"""

import hashlib
import sys
from typing import Any
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ── Pure generator tests ─────────────────────────────────────────────

from aas_generator import (
    _aas_id_for_lab,
    _submodel_id_for_fmu,
    _submodel_id_for_technical,
    _submodel_id_for_execution,
    _submodel_id_for_interfaces,
    _submodel_id_for_contact,
    _submodel_id_for_handover,
    _encode_id,
    _aas_resource_path,
    _fmi_type_to_idta,
    _causality_to_port_type,
    _sanitize_idshort,
    build_simulation_ports,
    build_simulation_submodel,
    build_technical_data_submodel,
    build_execution_capabilities_submodel,
    build_asset_interfaces_description_submodel,
    build_contact_information_submodel,
    build_handover_documentation_submodel,
    build_aas_shell,
    delete_aasx_resources,
    discover_basyx_shells,
    serialize_aasx_resources,
)

_aas_mod: Any = sys.modules["aas_generator"]


class TestAasIdGeneration:
    def test_aas_id_format(self):
        assert _aas_id_for_lab("42") == "urn:decentralabs:lab:42"

    def test_submodel_id_format(self):
        assert _submodel_id_for_fmu("42") == "urn:decentralabs:lab:42:sm:simulationModels"

    def test_standard_support_submodel_ids(self):
        assert _submodel_id_for_interfaces("42") == "urn:decentralabs:lab:42:sm:assetInterfaces"
        assert _submodel_id_for_contact("42") == "urn:decentralabs:lab:42:sm:contactInformation"
        assert _submodel_id_for_handover("42") == "urn:decentralabs:lab:42:sm:handoverDocumentation"

    def test_technical_submodel_id_format(self):
        assert _submodel_id_for_technical("42") == "urn:decentralabs:lab:42:sm:technicalData"

    def test_encode_id_roundtrip(self):
        raw = "urn:decentralabs:lab:42"
        encoded = _encode_id(raw)
        assert isinstance(encoded, str)
        assert "=" not in encoded
        # Must be valid base64url
        import base64
        decoded = base64.urlsafe_b64decode(encoded + "==").decode()
        assert decoded == raw

    @pytest.mark.parametrize("encoded_id", ["../etc/passwd", "urn:test/id", "shell?id=1"])
    def test_resource_path_rejects_untrusted_id(self, encoded_id):
        with pytest.raises(ValueError):
            _aas_resource_path("shells", encoded_id)


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
        connector = ports[0]
        assert connector["idShort"] == "Input"
        assert connector["semanticId"]["keys"][0]["value"].endswith("/PortsConnector/1/0")
        variable = connector["value"][1]
        values = {el["idShort"]: el for el in variable["value"]}
        assert values["VariableName"]["value"] == "force"
        assert values["VariableType"]["value"] == "Real"
        assert values["VariableCausality"]["value"] == "input"
        assert values["UnitList"]["value"] == "N"
        assert "DefaultValue" not in values

    def test_output_port_without_optional_fields(self):
        variables = [
            {"name": "velocity", "causality": "output", "type": "Float64", "variability": "continuous"},
        ]
        ports = build_simulation_ports(variables)
        connector = ports[0]
        variable = connector["value"][1]
        values = {el["idShort"]: el for el in variable["value"]}
        assert values["VariableName"]["value"] == "velocity"
        assert values["VariableType"]["value"] == "Real"
        assert values["VariableCausality"]["value"] == "output"
        assert values["UnitList"]["value"] == "others"

    def test_port_description_field(self):
        variables = [
            {"name": "force", "causality": "input", "type": "Real", "description": "Applied force"},
        ]
        ports = build_simulation_ports(variables)
        values = {el["idShort"]: el for el in ports[0]["value"][1]["value"]}
        assert "VariableDescription" in values
        assert values["VariableDescription"]["value"][0]["text"] == "Applied force"

    def test_quantity_kind_field(self):
        variables = [
            {"name": "mass", "causality": "input", "type": "Real", "quantity": "Mass"},
        ]
        ports = build_simulation_ports(variables)
        values = {el["idShort"]: el for el in ports[0]["value"][1]["value"]}
        assert "UnitDescription" in values
        assert values["UnitDescription"]["value"][0]["text"] == "Mass"


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
        assert sm["semanticId"]["keys"][0]["value"] == "https://admin-shell.io/idta/SubmodelTemplate/SimulationModels/1/1"

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
        assert sim_model["displayName"][0]["text"] == "TestModel"
        assert props["TypeOfModel"]["value"] == "CoSimulation"
        assert props["DefaultSimTime"]["value"] == "10.0"
        model_file = {el["idShort"]: el for el in props["ModelFile"]["value"]}
        assert model_file["ModelFileType"]["value"] == "FMI 3.0, Co-Simulation"
        assert "AccessKey" not in props
        assert "SyncTimestamp" not in props

    def test_ports_included_for_io_variables(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        sim_model = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in sim_model["value"]}
        assert "Ports" in props
        ports_coll = props["Ports"]
        # One standard connector per FMI causality, local variables omitted.
        assert len(ports_coll["value"]) == 2
        connector_names = {p["idShort"] for p in ports_coll["value"]}
        assert connector_names == {"Input", "Output"}

    def test_no_ports_when_only_locals(self):
        metadata = {**SAMPLE_METADATA, "modelVariables": [
            {"name": "x", "causality": "local", "type": "Real"},
        ]}
        sm = build_simulation_submodel("42", "test.fmu", metadata)
        sim_model = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in sim_model["value"]}
        assert "Ports" not in props

    def test_summary_from_extra_info_description(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"description": "My lab model"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "Summary" in props
        assert props["Summary"]["modelType"] == "MultiLanguageProperty"
        assert props["Summary"]["value"][0]["language"] == "en"
        assert props["Summary"]["value"][0]["text"] == "My lab model"

    def test_summary_from_metadata_description_fallback(self):
        metadata_with_desc = {**SAMPLE_METADATA, "description": "FMU description"}
        sm = build_simulation_submodel("42", "test.fmu", metadata_with_desc)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "Summary" in props
        assert props["Summary"]["value"][0]["text"] == "FMU description"

    def test_summary_extra_info_overrides_metadata(self):
        metadata_with_desc = {**SAMPLE_METADATA, "description": "FMU description"}
        sm = build_simulation_submodel("42", "test.fmu", metadata_with_desc, {"description": "Provider override"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert props["Summary"]["value"][0]["text"] == "Provider override"

    def test_no_summary_when_no_description(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "Summary" not in props

    def test_model_file_always_present(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "ModelFile" in props
        assert props["ModelFile"]["modelType"] == "SubmodelElementCollection"
        model_file = {el["idShort"]: el for el in props["ModelFile"]["value"]}
        model_version = {el["idShort"]: el for el in model_file["ModelFileVersion"]["value"]}
        assert model_version["DigitalFile"]["contentType"] == "application/zip"
        assert model_version["DigitalFile"]["value"] == "/fmu-data/test.fmu"
        assert "extensions" not in model_version["DigitalFile"]

    def test_model_file_with_sha256(self, tmp_path, monkeypatch):
        import hashlib
        fmu = tmp_path / "test.fmu"
        fmu.write_bytes(b"fake-fmu-content")
        monkeypatch.setattr(_aas_mod, "FMU_DATA_PATH", str(tmp_path))
        expected_sha = hashlib.sha256(b"fake-fmu-content").hexdigest()
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, fmu_path=fmu)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "ModelFile" in props
        model_file = {el["idShort"]: el for el in props["ModelFile"]["value"]}
        model_version = {el["idShort"]: el for el in model_file["ModelFileVersion"]["value"]}
        sha_ext = next((e for e in model_version["DigitalFile"].get("extensions", []) if e["name"] == "sha256"), None)
        assert sha_ext is not None
        assert sha_ext["value"] == expected_sha

    def test_model_file_hash_never_reads_same_named_file_outside_root(self, tmp_path, monkeypatch):
        inside = tmp_path / "test.fmu"
        inside.write_bytes(b"inside-fmu-content")
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
        outside_dir.mkdir()
        outside = outside_dir / "test.fmu"
        outside.write_bytes(b"outside-fmu-content")
        monkeypatch.setattr(_aas_mod, "FMU_DATA_PATH", str(tmp_path))

        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, fmu_path=outside)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        model_file = {el["idShort"]: el for el in props["ModelFile"]["value"]}
        model_version = {el["idShort"]: el for el in model_file["ModelFileVersion"]["value"]}
        sha_ext = next((e for e in model_version["DigitalFile"].get("extensions", []) if e["name"] == "sha256"), None)

        assert sha_ext is not None
        assert sha_ext["value"] == hashlib.sha256(b"inside-fmu-content").hexdigest()

    def test_simulation_tool_support_structure(self):
        metadata = {**SAMPLE_METADATA, "generationTool": "Modelica v4.1", "fmiVersion": "3.0"}
        sm = build_simulation_submodel("42", "test.fmu", metadata)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "GenerationTool" not in props  # flat property must not exist
        assert "Environment" in props
        environment = {el["idShort"]: el for el in props["Environment"]["value"]}
        tool_props = {el["idShort"]: el for el in environment["SimulationTool"]["value"]}
        assert tool_props["SimToolName"]["value"] == "Modelica v4.1"

    def test_no_simulation_tool_support_when_no_gen_tool(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "Environment" in props  # default solver metadata is still standard
        assert "GenerationTool" not in props

    def test_tolerance_idshort(self):
        metadata = {**SAMPLE_METADATA, "defaultTolerance": 1e-4}
        sm = build_simulation_submodel("42", "test.fmu", metadata)
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        environment = {el["idShort"]: el for el in props["Environment"]["value"]}
        solver = {el["idShort"]: el for el in environment["SimulationTool"]["value"]}["SolverAndTolerances"]
        solver_props = {el["idShort"]: el for el in solver["value"]}
        assert solver_props["Tolerance"]["value"] == "0.0001"
        assert "DefaultTolerance" not in props  # old non-conformant idShort must not exist


class TestBuildExecutionCapabilitiesSubmodel:
    def test_submodel_describes_reservation_scoped_fmu_execution(self):
        sm = build_execution_capabilities_submodel("42", SAMPLE_METADATA, {
            "status": "UP",
            "backendMode": "station",
        })

        assert sm["id"] == "urn:decentralabs:lab:42:sm:executionCapabilities"
        assert sm["idShort"] == "CapabilityDescription"
        capabilities = []
        for container in sm["submodelElements"][0]["value"]:
            capabilities.extend(container["value"])
        operation_names = {capability["idShort"] for capability in capabilities}
        assert {"RunSimulation", "CancelSimulation", "CreateRealtimeSession", "Reset", "Step", "GetOutputs"}.issubset(operation_names)

        payload_text = str(sm).lower()
        assert "st_secret" not in payload_text
        assert "capabilitydescription" in payload_text

    def test_realtime_capabilities_are_omitted_without_co_simulation(self):
        metadata = {**SAMPLE_METADATA, "supportsCoSimulation": False, "supportsModelExchange": True}
        sm = build_execution_capabilities_submodel("42", metadata)
        operation_names = {
            capability["idShort"]
            for container in sm["submodelElements"][0]["value"]
            for capability in container["value"]
        }
        assert "RunSimulation" in operation_names
        assert "CreateRealtimeSession" not in operation_names


class TestStandardSupportSubmodels:
    def test_asset_interfaces_describe_actions(self):
        sm = build_asset_interfaces_description_submodel("42", [("Reset", "/fmu/api/v1/fmu/sessions", "GET", "websocket")])
        assert sm["semanticId"]["keys"][0]["value"].endswith("AssetInterfacesDescription/1/1/Submodel")
        actions = sm["submodelElements"][0]["value"][2]["value"][0]["value"]
        assert actions[0]["idShort"] == "Reset"
        assert actions[0]["semanticId"]["keys"][0]["value"].endswith("ActionAffordance")

    def test_contact_and_handover_use_standard_templates(self):
        contact = build_contact_information_submodel("42", {"contactEmail": "lab@example.com"})
        assert contact["semanticId"]["keys"][0]["value"].endswith("ContactInformations")
        handover = build_handover_documentation_submodel("42", {"documentationUrls": ["https://example.com/doc"]})
        assert handover["semanticId"]["keys"][0]["value"] == "0173-1#01-AHF578#003"


SAMPLE_UNIT_DEFS = [
    {"name": "rad/s"},
    {
        "name": "N\u00b7m",
        "baseUnit": {"m": 2, "kg": 1, "s": -2},
        "displayUnits": [{"name": "kN\u00b7m", "factor": 1000.0}],
    },
]


class TestSanitizeIdShort:
    @pytest.mark.parametrize("name,expected", [
        ("m/s", "m_s"),
        ("N\u00b7m", "N_m"),
        ("rad/s", "rad_s"),
        ("1/s", "u1_s"),
        ("myUnit", "myUnit"),
        ("", "Unit"),
    ])
    def test_sanitize_common_cases(self, name, expected):
        assert _sanitize_idshort(name) == expected


@pytest.mark.skip(reason="UnitDefinitions custom submodel was replaced by standard IDTA 02005 unit fields")
class TestBuildUnitDefinitionsSubmodel:
    def test_submodel_structure(self):
        sm = build_unit_definitions_submodel("42", SAMPLE_UNIT_DEFS)
        assert sm["id"] == "urn:decentralabs:lab:42:sm:unitDefinitions"
        assert sm["idShort"] == "UnitDefinitions"
        assert sm["modelType"] == "Submodel"
        assert len(sm["submodelElements"]) == 2

    def test_unit_idshort_sanitized(self):
        sm = build_unit_definitions_submodel("42", [{"name": "rad/s"}])
        elem = sm["submodelElements"][0]
        assert elem["idShort"] == "rad_s"
        assert elem["modelType"] == "SubmodelElementCollection"
        props = {el["idShort"]: el for el in elem["value"]}
        assert props["Name"]["value"] == "rad/s"

    def test_base_unit_exponents(self):
        sm = build_unit_definitions_submodel("42", [{"name": "N", "baseUnit": {"kg": 1, "m": 1, "s": -2}}])
        elem = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in elem["value"]}
        assert "BaseUnit" in props
        bu_props = {el["idShort"]: el for el in props["BaseUnit"]["value"]}
        assert bu_props["kg"]["value"] == "1"
        assert bu_props["m"]["value"] == "1"
        assert bu_props["s"]["value"] == "-2"
        assert "Factor" not in bu_props
        assert "Offset" not in bu_props

    def test_base_unit_factor(self):
        sm = build_unit_definitions_submodel("42", [{"name": "km", "baseUnit": {"m": 1, "factor": 1000.0}}])
        elem = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in elem["value"]}
        bu_props = {el["idShort"]: el for el in props["BaseUnit"]["value"]}
        assert bu_props["Factor"]["value"] == "1000.0"
        assert "Offset" not in bu_props

    def test_display_units(self):
        sm = build_unit_definitions_submodel("42", [{
            "name": "N",
            "displayUnits": [{"name": "kN", "factor": 1000.0}, {"name": "mN", "factor": 0.001}],
        }])
        elem = sm["submodelElements"][0]
        props = {el["idShort"]: el for el in elem["value"]}
        assert "DisplayUnits" in props
        du_ids = {el["idShort"] for el in props["DisplayUnits"]["value"]}
        assert "kN" in du_ids
        assert "mN" in du_ids
        du_by_id = {el["idShort"]: el for el in props["DisplayUnits"]["value"]}
        du_kN_props = {el["idShort"]: el for el in du_by_id["kN"]["value"]}
        assert du_kN_props["Name"]["value"] == "kN"
        assert du_kN_props["Factor"]["value"] == "1000.0"

    def test_no_base_unit_when_absent(self):
        sm = build_unit_definitions_submodel("42", [{"name": "count"}])
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "BaseUnit" not in props
        assert "DisplayUnits" not in props

    def test_duplicate_unit_names_get_unique_idshorts(self):
        # Two units whose sanitized names collide (e.g. "m/s" and "m_s")
        sm = build_unit_definitions_submodel("42", [{"name": "m/s"}, {"name": "m_s"}])
        ids = [el["idShort"] for el in sm["submodelElements"]]
        assert len(ids) == len(set(ids))  # all unique

    def test_empty_unit_defs_produces_empty_submodel(self):
        sm = build_unit_definitions_submodel("42", [])
        assert sm["submodelElements"] == []


class TestBuildAasShell:
    def test_shell_structure(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA)
        assert shell["id"] == "urn:decentralabs:lab:42"
        assert shell["modelType"] == "AssetAdministrationShell"
        assert shell["assetInformation"]["assetKind"] == "Instance"
        assert shell["assetInformation"]["globalAssetId"] == "urn:decentralabs:lab:42"
        assert "assetType" not in shell["assetInformation"]

    def test_shell_references_submodel(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA)
        refs = shell["submodels"]
        assert len(refs) == 6
        assert refs[0]["keys"][0]["value"] == "urn:decentralabs:lab:42:sm:simulationModels"
        assert refs[1]["keys"][0]["value"] == "urn:decentralabs:lab:42:sm:technicalData"

    def test_shell_extra_submodel_ids(self):
        extra = ["urn:decentralabs:lab:42:sm:providerExtension"]
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA, extra_submodel_ids=extra)
        ref_values = [r["keys"][0]["value"] for r in shell["submodels"]]
        assert "urn:decentralabs:lab:42:sm:simulationModels" in ref_values
        assert "urn:decentralabs:lab:42:sm:providerExtension" in ref_values
        assert "urn:decentralabs:lab:42:sm:technicalData" in ref_values
        assert len(shell["submodels"]) == 7

    def test_shell_no_extra_submodels_by_default(self):
        shell = build_aas_shell("42", "test.fmu", SAMPLE_METADATA)
        assert len(shell["submodels"]) == 6

    def test_shell_idshort_format(self):
        shell = build_aas_shell("7", "motor.fmu", SAMPLE_METADATA)
        assert shell["idShort"] == "DecentraLabs_Lab_7"


class TestExtraInfoFields:
    """Tests for optional extra_info fields in build_* functions and sync endpoint."""

    # -- build_simulation_submodel extra_info --

    def test_submodel_extra_info_license(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"license": "MIT"})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert props["LicenseModel"]["value"] == "MIT"

    def test_submodel_extra_info_documentation_url(self):
        sm = build_handover_documentation_submodel("42", {"documentationUrl": "https://example.com"})
        assert sm["submodelElements"][0]["value"][0]["value"][1]["value"][0]["value"][3]["value"][0]["value"] == "https://example.com"

    def test_submodel_extra_info_documentation_urls_preserves_all_links(self):
        sm = build_handover_documentation_submodel(
            "42", {"documentationUrls": ["https://example.com/manual.pdf", "https://example.com/guide.html"]}
        )
        files = [
            document["value"][1]["value"][0]["value"][3]["value"][0]["value"]
            for document in sm["submodelElements"][0]["value"]
        ]
        assert files == ["https://example.com/manual.pdf", "https://example.com/guide.html"]

    def test_submodel_extra_info_contact_email(self):
        sm = build_contact_information_submodel("42", {"contactEmail": "lab@example.com"})
        email = sm["submodelElements"][0]["value"][0]["value"][0]
        assert email["idShort"] == "EmailAddress"
        assert email["value"] == "lab@example.com"

    def test_submodel_extra_info_empty_fields_not_included(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, {"license": "", "documentationUrl": "  "})
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "LicenseModel" not in props

    def test_submodel_extra_info_none_is_noop(self):
        sm = build_simulation_submodel("42", "test.fmu", SAMPLE_METADATA, None)
        # No extra properties should be present
        props = {el["idShort"]: el for el in sm["submodelElements"][0]["value"]}
        assert "LicenseModel" not in props

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


class TestBuildTechnicalDataSubmodel:
    def test_exposes_common_fmu_operational_fields(self):
        submodel = build_technical_data_submodel(
            "42",
            SAMPLE_METADATA,
            {
                "status": "UP",
                "backendMode": "station",
                "activeSimulationCount": 2,
                "maxConcurrentSimulations": 10,
            },
        )
        assert submodel["id"] == "urn:decentralabs:lab:42:sm:technicalData"
        assert submodel["idShort"] == "TechnicalData"
        areas = submodel["submodelElements"][1]["value"][0]["value"]
        props = {element["idShort"]: element for element in areas}
        assert props["ResourceType"]["value"] == "FMU"
        assert props["ResourceStatus"]["value"] == "Ready"
        assert props["ReadyFlag"]["value"] == "true"
        assert props["ModelAvailable"]["value"] == "true"
        assert props["ExecutionBackend"]["value"] == "station"
        assert props["ActiveSimulationCount"]["value"] == "2"
        assert props["MaxConcurrentSimulations"]["value"] == "10"

    def test_unknown_runtime_status_does_not_claim_fmu_is_ready(self):
        submodel = build_technical_data_submodel("42", SAMPLE_METADATA)
        props = {element["idShort"]: element for element in submodel["submodelElements"][1]["value"][0]["value"]}
        assert props["ResourceStatus"]["value"] == "Unknown"
        assert props["ReadyFlag"]["value"] == ""
        assert props["ModelAvailable"]["value"] == "true"


# ── Endpoint integration tests ───────────────────────────────────────

from fastapi.testclient import TestClient


def _get_app():
    """Import app lazily to avoid polluting module-level state for other test files."""
    with patch("auth.verify_jwt", return_value={"sub": "test-user", "labId": 1, "accessKey": "test.fmu"}):
        from runner_application import app
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
    @patch("runner_application.read_model_description")
    @patch("runner_application._resolve_fmu_path")
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
    @patch("runner_application.read_model_description")
    @patch("runner_application._resolve_fmu_path")
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

    @patch("runner_application.read_model_description")
    @patch("runner_application._resolve_fmu_path")
    def test_sync_fmu_not_found(self, mock_resolve, mock_read_md):
        from fastapi import HTTPException as _H
        mock_resolve.side_effect = _H(status_code=404, detail="FMU file not found: nonexistent.fmu")

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/nonexistent.fmu/sync")
        assert resp.status_code == 404

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("runner_application.read_model_description")
    @patch("runner_application._resolve_fmu_path")
    def test_sync_basyx_error(self, mock_resolve, mock_read_md, mock_sync):
        mock_resolve.return_value = "/fake/path/test.fmu"
        mock_read_md.return_value = self._mock_model_description()
        mock_sync.return_value = {"error": "submodel creation failed: 500"}

        client = TestClient(_get_app())
        resp = client.post("/aas-admin/fmu/test.fmu/sync")
        assert resp.status_code == 502
        assert "submodel creation failed" in resp.json()["detail"]

    @patch("aas_generator.sync_fmu_to_basyx", new_callable=AsyncMock)
    @patch("runner_application.read_model_description")
    @patch("runner_application._resolve_fmu_path")
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
        _aas_mod.BASYX_AAS_URL = "https://127.0.0.1:19999"  # nothing listening here
        try:
            result = await _aas_mod.sync_fmu_to_basyx("42", "motor.fmu", SAMPLE_METADATA)
            assert "error" in result
            assert "BaSyx unreachable" in result["error"]
            assert result.get("synced") is None
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lab_id", ["../etc/passwd", "lab?id=1", "urn:decentralabs:lab:1"])
    async def test_rejects_invalid_lab_id_before_network(self, lab_id):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
        try:
            with patch("httpx.AsyncClient") as mock_client:
                result = await _aas_mod.sync_fmu_to_basyx(lab_id, "motor.fmu", SAMPLE_METADATA)

            assert result == {"error": "AAS lab ID rejected", "created": False, "updated": False}
            mock_client.assert_not_called()
        finally:
            _aas_mod.BASYX_AAS_URL = original


# ── _parse_aasx unit tests ──────────────────────────────────────────

class TestDeleteAasxResources:
    @pytest.mark.asyncio
    async def test_deletes_imported_submodels_and_shells_from_basyx(self):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
        try:
            mock_response = MagicMock(status_code=204, text="")
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await delete_aasx_resources(
                    shell_ids=["urn:test:shell:1"],
                    submodel_ids=["urn:test:sm:1", "urn:test:sm:2"],
                )

            assert result == {
                "deletedAasIds": ["urn:test:shell:1"],
                "deletedSubmodelIds": ["urn:test:sm:1", "urn:test:sm:2"],
                "failed": [],
            }
            assert [call.args[0] for call in mock_client.delete.await_args_list] == [
                f"/submodels/{_encode_id('urn:test:sm:1')}",
                f"/submodels/{_encode_id('urn:test:sm:2')}",
                f"/shells/{_encode_id('urn:test:shell:1')}",
            ]
        finally:
            _aas_mod.BASYX_AAS_URL = original


class TestSerializeAasxResources:
    @pytest.mark.asyncio
    async def test_serializes_catalog_resources_from_basyx(self):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
        try:
            mock_response = MagicMock(
                status_code=200,
                content=b"PK\x03\x04generated-aasx",
                headers={"content-type": "application/asset-administration-shell-package+xml"},
            )
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await serialize_aasx_resources(
                    shell_ids=["urn:test:shell:1"],
                    submodel_ids=["urn:test:sm:1"],
                )

            assert result["content"] == b"PK\x03\x04generated-aasx"
            assert result["mediaType"] == "application/asset-administration-shell-package+xml"
            request = mock_client.get.await_args
            assert request.args[0] == "/serialization"
            assert request.kwargs["params"] == [
                ("aasIds", _encode_id("urn:test:shell:1")),
                ("includeConceptDescriptions", "true"),
                ("submodelIds", _encode_id("urn:test:sm:1")),
            ]
            assert request.kwargs["headers"]["Accept"] == "application/asset-administration-shell-package+xml"
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_serialization_is_disabled_without_basyx(self):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = ""
        try:
            result = await serialize_aasx_resources(
                shell_ids=["urn:test:shell:1"],
                submodel_ids=[],
            )
            assert result["disabled"] is True
            assert result["error"] == "BaSyx is not configured"
        finally:
            _aas_mod.BASYX_AAS_URL = original

    @pytest.mark.asyncio
    async def test_reports_basyx_failure_without_claiming_the_resource_was_deleted(self):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
        try:
            mock_response = MagicMock(status_code=500, text="internal error")
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await delete_aasx_resources(
                    shell_ids=["urn:test:shell:1"],
                    submodel_ids=[],
                )

            assert result["deletedAasIds"] == []
            assert result["failed"] == [{
                "collection": "shells",
                "id": "urn:test:shell:1",
                "status": 500,
            }]
            assert result["error"] == "BaSyx resource deletion failed"
        finally:
            _aas_mod.BASYX_AAS_URL = original


class TestDiscoverBasyxShells:
    @pytest.mark.asyncio
    async def test_discovers_stable_lab_shells_and_reads_submodels_when_needed(self):
        original_url = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = _aas_mod._BUNDLED_AAS_URL
        try:
            list_response = MagicMock(status_code=200)
            list_response.json.return_value = {
                "result": [
                    {"id": "urn:decentralabs:lab:7"},
                    {"id": "urn:other:aas:8"},
                ]
            }
            detail_response = MagicMock(status_code=200)
            detail_response.json.return_value = {
                "id": "urn:decentralabs:lab:7",
                "submodels": [
                    {"keys": [{"type": "Submodel", "value": "urn:lab:7:sm"}]},
                ],
            }
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=[list_response, detail_response])

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await discover_basyx_shells()

            assert result == {
                "shells": [{
                    "id": "urn:decentralabs:lab:7",
                    "submodelIds": ["urn:lab:7:sm"],
                }]
            }
            assert [call.args[0] for call in mock_client.get.await_args_list] == [
                "/shells",
                f"/shells/{_encode_id('urn:decentralabs:lab:7')}",
            ]
        finally:
            _aas_mod.BASYX_AAS_URL = original_url


class TestSyncFmuToBasyxGenerated:
    @pytest.mark.asyncio
    async def test_generated_sync_publishes_common_technical_data(self):
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "http://basyx-aas-server:8081"
        try:
            mock_response = MagicMock(status_code=201)
            mock_client = AsyncMock()
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await _aas_mod.sync_fmu_to_basyx(
                    "42",
                    "motor.fmu",
                    SAMPLE_METADATA,
                    runtime_info={"status": "UP", "backendMode": "local"},
                )

            assert result["synced"] is True
            put_paths = [call.args[0] for call in mock_client.put.await_args_list]
            assert f"/submodels/{_encode_id(_submodel_id_for_fmu('42'))}" in put_paths
            assert f"/submodels/{_encode_id(_submodel_id_for_technical('42'))}" in put_paths
            assert f"/shells/{_encode_id(_aas_id_for_lab('42'))}" in put_paths

            technical_call = next(
                call for call in mock_client.put.await_args_list
                if call.args[0] == f"/submodels/{_encode_id(_submodel_id_for_technical('42'))}"
            )
            payload = technical_call.kwargs["json"]
            areas = {element["idShort"]: element for element in payload["submodelElements"]}["TechnicalPropertyAreas"]
            props = {element["idShort"]: element for element in areas["value"][0]["value"]}
            assert props["ResourceStatus"]["value"] == "Ready"
            assert props["ExecutionBackend"]["value"] == "local"
        finally:
            _aas_mod.BASYX_AAS_URL = original


import io
import json
import zipfile



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
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
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
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
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
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
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

    @pytest.mark.asyncio
    async def test_physical_aasx_upload_requires_the_stable_lab_shell_id(self):
        pkg = _make_aasx(
            shells=[{"id": "urn:custom:shell:physical"}],
            submodels=[{"id": "urn:custom:sm:physical"}],
        )
        original = _aas_mod.BASYX_AAS_URL
        _aas_mod.BASYX_AAS_URL = "https://basyx-test:8081"
        try:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await _aas_mod.sync_fmu_to_basyx(
                    "42",
                    "42",
                    {},
                    aasx_bytes=pkg,
                    required_aas_id="urn:decentralabs:lab:42",
                )

            assert result["error"] == (
                "AASX must contain shell urn:decentralabs:lab:42"
            )
            mock_client.put.assert_not_called()
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


# ── AAS Link CRUD endpoint tests ─────────────────────────────────────


class TestAasLinkEndpoints:
    """Tests for POST/GET/DELETE /aas-admin/fmu/{accessKey}/aas-link
    and GET /aas-admin/resolve-aas-id."""

    def _client(self):
        return TestClient(_get_app())

    # ── POST: create link ────────────────────────────────────────────

    def test_create_link_success(self, tmp_path):
        """POST with valid aasId saves a JSON file and returns it."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.post(
                "/aas-admin/fmu/motor.fmu/aas-link",
                json={"aasId": "urn:example:aas:motor-v2"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] is True
        assert data["aasId"] == "urn:example:aas:motor-v2"
        assert data["accessKey"] == "motor.fmu"

    def test_create_link_with_lab_id(self, tmp_path):
        """POST with labId writes both accessKey and labId-indexed files."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.post(
                "/aas-admin/fmu/motor.fmu/aas-link",
                json={"aasId": "urn:example:aas:motor-v2", "labId": "42"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["labId"] == "42"
        # Both files should exist
        assert (tmp_path / "motor.fmu.aas-link.json").is_file()
        assert (tmp_path / "42.aas-link.json").is_file()

    def test_create_link_persists_file(self, tmp_path):
        """POST writes a .aas-link.json file with the correct content."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            client.post(
                "/aas-admin/fmu/test.fmu/aas-link",
                json={"aasId": "urn:example:aas:test", "submodelIds": ["urn:example:sm:1"]},
            )
        link_file = tmp_path / "test.fmu.aas-link.json"
        assert link_file.is_file()
        import json as _json
        saved = _json.loads(link_file.read_text())
        assert saved["aasId"] == "urn:example:aas:test"
        assert saved["submodelIds"] == ["urn:example:sm:1"]

    def test_create_link_missing_aas_id(self, tmp_path):
        """POST without aasId returns 400."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.post("/aas-admin/fmu/test.fmu/aas-link", json={})
        assert resp.status_code == 400

    def test_create_link_invalid_json(self, tmp_path):
        """POST with non-JSON body returns 400."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.post(
                "/aas-admin/fmu/test.fmu/aas-link",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 400

    def test_create_link_rejects_path_traversal_in_lab_id(self, tmp_path):
        """A lab index must never be able to select a file outside the link store."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.post(
                "/aas-admin/fmu/test.fmu/aas-link",
                json={"aasId": "urn:example:aas:test", "labId": "../outside"},
            )
        assert resp.status_code == 400
        assert not (tmp_path.parent / "outside.aas-link.json").exists()

    # ── GET: read link ────────────────────────────────────────────────

    def test_get_link_exists(self, tmp_path):
        """GET returns the stored link."""
        import json as _json
        link_file = tmp_path / "motor.fmu.aas-link.json"
        link_file.write_text(_json.dumps({"aasId": "urn:example:aas:motor-v2"}))
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.get("/aas-admin/fmu/motor.fmu/aas-link")
        assert resp.status_code == 200
        data = resp.json()
        assert data["aasId"] == "urn:example:aas:motor-v2"
        assert data["accessKey"] == "motor.fmu"

    def test_get_link_not_found(self, tmp_path):
        """GET returns 404 when no link is configured."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.get("/aas-admin/fmu/nonexistent.fmu/aas-link")
        assert resp.status_code == 404

    # ── DELETE: remove link ───────────────────────────────────────────

    def test_delete_link_success(self, tmp_path):
        """DELETE removes the link file and returns unlinked:True."""
        import json as _json
        link_file = tmp_path / "test.fmu.aas-link.json"
        link_file.write_text(_json.dumps({"aasId": "urn:example:aas:test"}))
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.delete("/aas-admin/fmu/test.fmu/aas-link")
        assert resp.status_code == 200
        assert resp.json()["unlinked"] is True
        assert not link_file.exists()

    def test_delete_link_also_removes_lab_id_file(self, tmp_path):
        """DELETE cleans up the labId-indexed file when it was written by POST."""
        import json as _json
        link_content = {"aasId": "urn:example:aas:motor", "labId": "99"}
        (tmp_path / "motor.fmu.aas-link.json").write_text(_json.dumps(link_content))
        (tmp_path / "99.aas-link.json").write_text(_json.dumps(link_content))
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.delete("/aas-admin/fmu/motor.fmu/aas-link")
        assert resp.status_code == 200
        assert not (tmp_path / "motor.fmu.aas-link.json").exists()
        assert not (tmp_path / "99.aas-link.json").exists()

    def test_delete_link_not_found(self, tmp_path):
        """DELETE returns 404 when no link exists."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.delete("/aas-admin/fmu/ghost.fmu/aas-link")
        assert resp.status_code == 404

    # ── GET /aas-admin/resolve-aas-id ────────────────────────────────

    def test_resolve_returns_override(self, tmp_path):
        """resolve-aas-id returns override:True when a labId-indexed link exists."""
        import json as _json
        # Simulate what POST writes when labId="42" and accessKey="motor.fmu"
        link_file = tmp_path / "42.aas-link.json"
        link_file.write_text(_json.dumps({"aasId": "urn:external:aas:motor-model", "labId": "42"}))
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.get(
                "/aas-admin/resolve-aas-id",
                params={"shellId": "urn:decentralabs:lab:42"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["override"] is True
        assert data["targetId"] == "urn:external:aas:motor-model"

    def test_resolve_no_override(self, tmp_path):
        """resolve-aas-id returns override:False when no link exists."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.get(
                "/aas-admin/resolve-aas-id",
                params={"shellId": "urn:decentralabs:lab:99"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["override"] is False
        assert data["targetId"] == "urn:decentralabs:lab:99"

    def test_resolve_non_conventional_id(self, tmp_path):
        """resolve-aas-id passes through non-conventional IDs unchanged."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            resp = client.get(
                "/aas-admin/resolve-aas-id",
                params={"shellId": "urn:some-other-vendor:asset:xyz"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["override"] is False
        assert data["targetId"] == "urn:some-other-vendor:asset:xyz"

    def test_resolve_lab_id_with_fmu_fallback(self, tmp_path):
        """resolve-aas-id tries labKey.fmu when labKey alone has no link (accessKey-only case)."""
        import json as _json
        # Provider created link without labId — stored only as motor.fmu.aas-link.json
        link_file = tmp_path / "motor.fmu.aas-link.json"
        link_file.write_text(_json.dumps({"aasId": "urn:external:motor"}))
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            # Shell ID was built without labId override: urn:decentralabs:lab:motor.fmu
            resp = client.get(
                "/aas-admin/resolve-aas-id",
                params={"shellId": "urn:decentralabs:lab:motor.fmu"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["override"] is True
        assert data["targetId"] == "urn:external:motor"

    def test_create_and_resolve_roundtrip(self, tmp_path):
        """Create a link with labId then resolve by the conventional shell ID."""
        with patch("runner_application._AAS_LINK_DATA_PATH", tmp_path):
            client = self._client()
            # Provider syncs with labId=7; stores link with labId=7
            client.post(
                "/aas-admin/fmu/turbine.fmu/aas-link",
                json={"aasId": "urn:provider:aas:turbine-v3", "labId": "7"},
            )
            # Marketplace queries urn:decentralabs:lab:7 (numeric labId)
            resp = client.get(
                "/aas-admin/resolve-aas-id",
                params={"shellId": "urn:decentralabs:lab:7"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["override"] is True
        assert data["targetId"] == "urn:provider:aas:turbine-v3"
