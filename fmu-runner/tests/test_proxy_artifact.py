import hashlib
import hmac
import io
import json
import zipfile

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
