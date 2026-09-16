from dataclasses import FrozenInstanceError

import pytest

from winrm_trust_context import WinRMTrustContext
from winrm_trust_runtime import WinRMTrustRuntime, create_winrm_trust_runtime


def _context(**overrides):
    values = {
        "normalize_winrm_trust_ref": lambda value: "pc-siemens",
        "trust_http_status": lambda code: {"known": 422}.get(code, 400),
        "winrm_trust_error_payload": lambda host, code: {"host": host, "code": code},
        "winrm_trust_ref_for_host": lambda host: "pc-siemens",
        "winrm_trust_root": lambda: "/trust",
        "winrm_trust_file_path": lambda host, filename: f"/trust/{filename}",
        "winrm_trust_certificate_path": lambda host: "/trust/server.cer",
        "winrm_trust_pem_path": lambda host: "/trust/server.pem",
        "parse_winrm_certificate": lambda path: "certificate",
        "parse_winrm_certificate_bytes": lambda raw: "parsed",
        "winrm_trust_metadata_path": lambda host: "/trust/metadata.json",
        "write_winrm_trust_bytes": lambda path, content: None,
        "read_winrm_trust_metadata": lambda host: {"source": "test"},
        "write_winrm_trust_metadata": lambda host, metadata: None,
        "validate_winrm_certificate": lambda certificate, host: {"status": "ready"},
        "read_winrm_certificate_upload": lambda: b"raw",
        "winrm_trust_request_value": lambda name: "value",
        "winrm_certificate_response_metadata": lambda certificate, host, input_format: {
            "status": "ready"
        },
        "store_winrm_trust_certificate": lambda host, certificate: {"status": "stored"},
        "delete_winrm_trust_certificate": lambda host: None,
        "materialize_winrm_pem": lambda host, certificate: "/trust/server.pem",
        "inspect_winrm_trust": lambda host: {"status": "ready"},
        "load_winrm_trust": lambda host: ("/trust/server.pem", {"status": "ready"}),
        "refresh_winrm_trust_store": lambda hosts: {"host": {"status": "missing"}},
    }
    values.update(overrides)
    return WinRMTrustContext(**values)


def test_winrm_trust_runtime_forwards_explicit_operations():
    runtime = create_winrm_trust_runtime(_context())

    assert isinstance(runtime, WinRMTrustRuntime)
    assert runtime.normalize_winrm_trust_ref("PC-Siemens") == "pc-siemens"
    assert runtime.trust_http_status("known") == 422
    assert runtime.winrm_trust_error_payload("host", "WINRM_TRUST_INVALID") == {
        "host": "host",
        "code": "WINRM_TRUST_INVALID",
    }
    assert runtime.winrm_trust_ref_for_host({"name": "PC-Siemens"}) == "pc-siemens"
    assert runtime.winrm_trust_root() == "/trust"
    assert runtime.winrm_trust_file_path({}, "server.cer") == "/trust/server.cer"
    assert runtime.winrm_trust_certificate_path({}) == "/trust/server.cer"
    assert runtime.winrm_trust_pem_path({}) == "/trust/server.pem"
    assert runtime.parse_winrm_certificate("/trust/server.cer") == "certificate"
    assert runtime.parse_winrm_certificate_bytes(b"raw") == "parsed"
    assert runtime.winrm_trust_metadata_path({}) == "/trust/metadata.json"
    assert runtime.read_winrm_trust_metadata({}) == {"source": "test"}
    assert runtime.validate_winrm_certificate("certificate", {}) == {"status": "ready"}
    assert runtime.read_winrm_certificate_upload() == b"raw"
    assert runtime.winrm_trust_request_value("fingerprintSha256") == "value"
    assert runtime.winrm_certificate_response_metadata("certificate", {}, "DER") == {
        "status": "ready"
    }
    assert runtime.store_winrm_trust_certificate({}, "certificate") == {"status": "stored"}
    assert runtime.delete_winrm_trust_certificate({}) is None
    assert runtime.materialize_winrm_pem({}, "certificate") == "/trust/server.pem"
    assert runtime.inspect_winrm_trust({}) == {"status": "ready"}
    assert runtime.load_winrm_trust({}) == ("/trust/server.pem", {"status": "ready"})
    assert runtime.refresh_winrm_trust_store([{"name": "host"}]) == {
        "host": {"status": "missing"}
    }


def test_winrm_trust_runtime_resolves_mutable_context_callbacks():
    root = "/first"
    calls = []
    context = _context(
        winrm_trust_root=lambda: root,
        refresh_winrm_trust_store=lambda hosts: calls.append((hosts, root)) or {},
    )
    runtime = create_winrm_trust_runtime(context)
    root = "/second"

    runtime.refresh_winrm_trust_store([{"name": "host"}])

    assert calls == [([{"name": "host"}], "/second")]


def test_winrm_trust_context_is_immutable():
    context = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "winrm_trust_root", lambda: "/changed")
