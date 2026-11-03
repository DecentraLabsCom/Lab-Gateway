import hashlib
import hmac
import io
import json
import zipfile
import xml.etree.ElementTree as ET

from proxy_artifact import build_proxy_artifact, build_proxy_artifact_headers


def test_build_proxy_artifact_preserves_archive_contract(tmp_path):
    model_xml = b"<?xml version='1.0'?><fmiModelDescription/>"
    runtime_file = tmp_path / "decentralabs_proxy.so"
    runtime_file.write_bytes(b"proxy-runtime")
    config = {
        "protocolVersion": "1.0",
        "fmiVersion": "2.0.3",
        "gatewayWsUrl": "wss://gateway.example/fmu/api/v1/fmu/sessions",
        "labId": "42",
        "reservationKey": "0xabc",
        "sessionTicket": "st_ticket_1",
        "ticketExpiresAt": 4102444800,
        "timeMode": "simtime",
    }

    artifact = build_proxy_artifact(
        model_xml=model_xml,
        config_payload=config,
        runtime_files=[(runtime_file, "binaries/linux64/decentralabs_proxy.so")],
    )

    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        assert archive.namelist() == [
            "modelDescription.xml",
            "resources/modelDescription.xml",
            "resources/config.json",
            "binaries/linux64/decentralabs_proxy.so",
        ]
        assert archive.read("modelDescription.xml") == model_xml
        assert archive.read("resources/modelDescription.xml") == model_xml
        assert json.loads(archive.read("resources/config.json")) == config
        assert archive.read("binaries/linux64/decentralabs_proxy.so") == b"proxy-runtime"


def test_build_proxy_artifact_declares_ref_and_struct_manifest_metadata(tmp_path):
    model_xml = (
        b"<?xml version='1.0'?><fmiModelDescription fmiVersion='3.0'>"
        b"<ModelVariables><Float64 name='domain' valueReference='1'/>"
        b"<Float64 name='result' valueReference='2'/></ModelVariables></fmiModelDescription>"
    )
    runtime_file = tmp_path / "decentralabs_proxy.so"
    runtime_file.write_bytes(b"proxy-runtime")

    artifact = build_proxy_artifact(
        model_xml=model_xml,
        config_payload={"protocolVersion": "1.0"},
        runtime_files=[(runtime_file, "binaries/linux64/decentralabs_proxy.so")],
        fmi_ls_parameter_sets=[
            {"name": "Nominal", "parameters": {"gain": 2.0}},
        ],
        fmi_ls_experiments=[],
        fmi_ls_model_metadata={
            "modelVariables": [
                {"name": "gain", "type": "Real", "causality": "parameter"},
            ],
        },
        fmi_ls_struct={
            "manifestName": "org.fmi-standard.fmi-ls-struct",
            "manifestVersion": "1.0.0-rc.1",
            "maps": [{
                "name": "response",
                "terminalKind": "org.fmi-standard.fmi-ls-struct.map.rectilinearGrid",
                "matchingRule": "org.fmi-standard.fmi-ls-struct.map",
                "members": [
                    {
                        "variableName": "domain",
                        "memberName": "time",
                        "variableKind": "org.fmi-standard.fmi-ls-struct.map.domain",
                    },
                    {
                        "variableName": "result",
                        "memberName": "response",
                        "variableKind": "org.fmi-standard.fmi-ls-struct.map.codomain",
                    },
                ],
            }],
        },
    )

    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        ref = ET.fromstring(archive.read(
            "extra/org.fmi-standard.fmi-ls-ref/fmi-ls-manifest.xml",
        ))
        struct = ET.fromstring(archive.read(
            "extra/org.fmi-standard.fmi-ls-struct/fmi-ls-manifest.xml",
        ))

    assert ref.attrib["{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-name"] == "org.fmi-standard.fmi-ls-ref"
    assert ref.attrib["{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-version"] == "1.0.0-alpha.1"
    assert ref.attrib["{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-description"] == (
        "Layered Standard providing information on related files included in an FMU."
    )
    related = ref.find("./Related")
    assert related is not None
    assert related.attrib["type"] == "application/x-ssp-parameter-set"
    assert struct.attrib["{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-name"] == "org.fmi-standard.fmi-ls-struct"
    assert struct.attrib["{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-description"] == (
        "Layered standard for structuring of variables"
    )


def test_build_proxy_artifact_headers_preserve_hash_and_signature_contract():
    artifact = b"proxy-artifact"

    headers = build_proxy_artifact_headers(
        artifact_bytes=artifact,
        lab_id="42",
        signing_key="top-secret",
    )

    assert headers["Content-Disposition"] == 'attachment; filename="fmu-proxy-lab-42.fmu"'
    assert headers["X-Proxy-Artifact-Sha256"] == hashlib.sha256(artifact).hexdigest()
    expected_signature = hmac.new(b"top-secret", artifact, hashlib.sha256).hexdigest()
    assert headers["X-Proxy-Artifact-Signature"] == f"hmac-sha256={expected_signature}"


def test_build_proxy_artifact_headers_omits_signature_without_key():
    headers = build_proxy_artifact_headers(
        artifact_bytes=b"proxy-artifact",
        lab_id="42",
        signing_key="",
    )

    assert "X-Proxy-Artifact-Signature" not in headers
