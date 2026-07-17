"""Focused contracts for branches exercised by dependency-upgrade CI."""

import hashlib
import asyncio
import io
import json
from pathlib import Path
import zipfile

from fastapi import HTTPException
import pytest

import aas_generator as aas
import auth


def test_aas_request_headers_support_bundled_and_allowlisted_external_services(monkeypatch):
    monkeypatch.setattr(aas, "BASYX_AAS_URL", "http://basyx-aas-server:8081/")
    assert aas._aas_request_headers() == {}

    monkeypatch.setattr(aas, "BASYX_AAS_URL", "https://aas.example/api")
    monkeypatch.setattr(aas, "AAS_ALLOWED_HOSTS", " other.example, aas.example ")
    monkeypatch.setattr(aas, "AAS_SERVICE_TOKEN", "service-secret")

    monkeypatch.setattr(aas, "AAS_SERVICE_TOKEN_HEADER", "X-AAS-Token")
    assert aas._aas_request_headers() == {"X-AAS-Token": "service-secret"}

    monkeypatch.setattr(aas, "AAS_SERVICE_TOKEN_HEADER", "Authorization")
    assert aas._aas_request_headers() == {"Authorization": "Bearer service-secret"}


@pytest.mark.parametrize(
    ("endpoint", "allowed_hosts", "token", "header", "message"),
    [
        ("http://aas.example", "aas.example", "secret", "Authorization", "HTTPS"),
        ("https://user:password@aas.example", "aas.example", "secret", "Authorization", "userinfo"),
        ("https://other.example", "aas.example", "secret", "Authorization", "allowlisted"),
        ("https://aas.example", "aas.example", "test", "Authorization", "missing"),
        ("https://aas.example", "aas.example", "secret", "bad_header", "invalid"),
    ],
)
def test_aas_request_headers_reject_unsafe_external_configuration(
    monkeypatch, endpoint, allowed_hosts, token, header, message
):
    monkeypatch.setattr(aas, "BASYX_AAS_URL", endpoint)
    monkeypatch.setattr(aas, "AAS_ALLOWED_HOSTS", allowed_hosts)
    monkeypatch.setattr(aas, "AAS_SERVICE_TOKEN", token)
    monkeypatch.setattr(aas, "AAS_SERVICE_TOKEN_HEADER", header)

    with pytest.raises(ValueError, match=message):
        aas._aas_request_headers()


def test_aas_identifier_validation_rejects_invalid_values():
    with pytest.raises(ValueError, match="lab ID"):
        aas._validate_lab_id("../lab")
    with pytest.raises(ValueError, match="resource path"):
        aas._aas_resource_path("unknown", "safe-id")

    assert aas._validate_lab_id("lab_42") == "lab_42"
    assert aas._aas_resource_path("shells", "safe-id") == "/shells/safe-id"


def test_fmu_digest_finds_nested_file_and_ignores_unsafe_or_missing_names(tmp_path, monkeypatch):
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    fmu = provider_dir / "model.fmu"
    payload = b"test-fmu"
    fmu.write_bytes(payload)
    (tmp_path / "unrelated.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr(aas, "FMU_DATA_PATH", str(tmp_path))

    assert aas._fmu_digest(Path("model.fmu")) == hashlib.sha256(payload).hexdigest()
    assert aas._fmu_digest(Path("model.txt")) == ""
    assert aas._fmu_digest(Path("missing.fmu")) == ""


def test_simulation_ports_render_all_optional_metadata():
    ports = aas.build_simulation_ports(
        [
            {
                "name": "force",
                "causality": "input",
                "type": "Float64",
                "variability": "discrete",
                "unit": "N",
                "start": 2.5,
                "quantity": "Force",
                "displayUnit": "kN",
                "nominal": 10.0,
                "description": "Applied force",
            }
        ]
    )
    values = {element["idShort"]: element["value"] for element in ports[0]["value"]}
    assert values["PortVariability"] == "discrete"
    assert values["DefaultValue"] == "2.5"
    assert values["QuantityKind"] == "Force"
    assert values["DisplayUnit"] == "kN"
    assert values["NominalValue"] == "10.0"
    assert values["PortDescription"] == "Applied force"


def test_simulation_submodel_renders_embedded_capabilities_and_provider_metadata(tmp_path, monkeypatch):
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    fmu_path = provider_dir / "model.fmu"
    fmu_path.write_bytes(b"model")
    monkeypatch.setattr(aas, "FMU_DATA_PATH", str(tmp_path))

    metadata = {
        "modelName": "Model",
        "fmiVersion": "3.0",
        "author": "Author",
        "version": "1.2.3",
        "generationTool": "Tool 1.0",
        "defaultTolerance": 0.0001,
        "capabilities": {
            "canGetAndSetFMUstate": True,
            "canSerializeFMUstate": False,
            "canHandleVariableCommunicationStepSize": True,
            "providesDirectionalDerivative": False,
            "providesAdjointDerivatives": True,
            "fixedInternalStepSize": 0.01,
        },
        "modelVariables": [],
    }
    extra_info = {
        "description": "Provider description",
        "license": "MIT",
        "documentationUrl": "https://docs.example/model",
        "contactEmail": "owner@example",
    }

    submodel = aas.build_simulation_submodel(
        "lab-42", "model.fmu", metadata, extra_info, fmu_path=fmu_path
    )
    properties = {element["idShort"]: element for element in submodel["submodelElements"][0]["value"]}

    assert properties["Author"]["value"] == "Author"
    assert properties["Version"]["value"] == "1.2.3"
    assert properties["SimulationToolSupport"]["value"][0]["value"][0]["value"] == "Tool 1.0"
    assert properties["Tolerance"]["value"] == "0.0001"
    assert properties["Capabilities"]["value"][-1]["idShort"] == "FixedInternalStepSize"
    assert properties["License"]["value"] == "MIT"
    assert properties["DocumentationUrl"]["value"] == "https://docs.example/model"
    assert properties["ContactEmail"]["value"] == "owner@example"
    assert properties["ModelFile"]["extensions"][0]["value"] == hashlib.sha256(b"model").hexdigest()


def test_unit_definitions_render_offsets_and_duplicate_display_names():
    submodel = aas.build_unit_definitions_submodel(
        "lab-42",
        [
            {
                "name": "temperature",
                "baseUnit": {"K": 1, "factor": 1.0, "offset": 273.15},
                "displayUnits": [
                    {"name": "degC", "offset": 273.15},
                    {"name": "degC", "factor": 2.0, "offset": 1.0},
                ],
            }
        ],
    )
    unit = submodel["submodelElements"][0]
    properties = {element["idShort"]: element for element in unit["value"]}
    base = {element["idShort"]: element for element in properties["BaseUnit"]["value"]}
    assert base["Offset"]["value"] == "273.15"
    displays = properties["DisplayUnits"]["value"]
    assert [display["idShort"] for display in displays] == ["degC", "degC_1"]
    assert {element["idShort"] for element in displays[1]["value"]} == {"Name", "Factor", "Offset"}


def test_auth_rejects_malformed_issuer_and_accepts_private_http_hosts():
    assert auth._is_loopback_or_private_host("10.0.0.4:8080") is True
    assert auth._is_loopback_or_private_host("172.16.0.4") is True
    assert auth._is_loopback_or_private_host("a.b.c.d") is False
    assert auth._build_jwks_url_from_issuer("http://10.0.0.4:8080/auth") == (
        "http://10.0.0.4:8080/auth/jwks"
    )
    with pytest.raises(ValueError, match="Invalid issuer URL"):
        auth._build_jwks_url_from_issuer("not-an-issuer")


def test_verify_jwt_token_requires_configured_audience(monkeypatch):
    monkeypatch.setattr(auth, "JWT_AUDIENCE", None)
    with pytest.raises(HTTPException, match="audience validation"):
        asyncio.run(auth.verify_jwt_token("unused"))


def test_parse_aasx_falls_back_after_corrupt_relationships_and_json():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("_rels/.rels", "not-xml")
        package.writestr("aasx/broken.json", "not-json")
        package.writestr("[Content_Types].xml", json.dumps({"ignored": True}))

    assert aas._parse_aasx(buffer.getvalue()) == {
        "shells": [],
        "submodels": [],
        "conceptDescriptions": [],
    }
