from types import SimpleNamespace

from winrm_trust_runtime import WinRMTrustRuntime, create_winrm_trust_runtime


def test_winrm_trust_runtime_forwards_paths_validation_and_loading():
    calls = []
    providers = {
        "_normalize_trust_ref_impl": lambda value, **kwargs: calls.append(
            ("normalize", value, kwargs)
        ) or "pc-siemens",
        "secure_filename": "secure",
        "WINRM_TRUST_REF_RE": "pattern",
        "_trust_ref_for_host_impl": lambda host, **kwargs: calls.append(
            ("ref", host, kwargs)
        ) or "pc-siemens",
        "normalize_winrm_trust_ref": lambda value: "pc-siemens",
        "_resolve_trust_root_impl": lambda path, **kwargs: calls.append(
            ("root", path, kwargs)
        ) or "/trust",
        "OPS_WINRM_TRUST_PATH": "/configured-trust",
        "os": SimpleNamespace(path=SimpleNamespace(realpath="realpath", abspath="abspath", isfile="isfile")),
        "WinRMTrustError": RuntimeError,
        "WINRM_CERTIFICATE_INVALID_MESSAGE": "invalid",
        "_resolve_trust_file_path_impl": lambda host, filename, **kwargs: calls.append(
            ("path", host, filename, kwargs)
        ) or f"/trust/{filename}",
        "_resolve_winrm_trust_file_path": "resolve",
        "_winrm_trust_root": lambda: "/trust",
        "_winrm_trust_file_path": lambda host, filename: f"/trust/{filename}",
        "winrm_trust_ref_for_host": lambda host: "pc-siemens",
        "WINRM_TRUST_CERTIFICATE_NAME": "server.cer",
        "WINRM_TRUST_PEM_NAME": "server.pem",
        "WINRM_TRUST_METADATA_NAME": "metadata.json",
        "_read_trust_certificate_impl": lambda path, **kwargs: calls.append(
            ("read-cert", path, kwargs)
        ) or "certificate",
        "WINRM_CERTIFICATE_MAX_BYTES": 4096,
        "_parse_winrm_certificate_bytes": lambda raw: calls.append(("parse-bytes", raw)) or "parsed",
        "_parse_winrm_certificate_bytes_impl": lambda raw, **kwargs: calls.append(
            ("parse", raw, kwargs)
        ) or "parsed",
        "_write_trust_bytes_impl": lambda path, content: calls.append(("write", path, content)),
        "_read_trust_metadata_file": lambda path: calls.append(("read-meta", path)) or {"source": "test"},
        "_winrm_trust_metadata_path": lambda host: "/trust/metadata.json",
        "_write_trust_metadata_file": lambda path, metadata, **kwargs: calls.append(
            ("write-meta", path, metadata, kwargs)
        ),
        "_validate_winrm_certificate_impl": lambda *args, **kwargs: calls.append(
            ("validate", args, kwargs)
        ) or {"status": "ready"},
        "_certificate_matches_host": "matches",
        "_winrm_certificate_metadata": "metadata",
        "WINRM_TRUST_ERROR_MESSAGES": {"WINRM_TRUST_INVALID": "invalid"},
        "_certificate_response_metadata_impl": lambda *args, **kwargs: calls.append(
            ("response-meta", args, kwargs)
        ) or {"status": "ready"},
    }
    runtime = create_winrm_trust_runtime(providers)

    assert isinstance(runtime, WinRMTrustRuntime)
    assert runtime.normalize_winrm_trust_ref("PC-Siemens") == "pc-siemens"
    assert runtime.winrm_trust_ref_for_host({"name": "PC-Siemens"}) == "pc-siemens"
    assert runtime.winrm_trust_root() == "/trust"
    assert runtime.winrm_trust_file_path({}, "server.cer") == "/trust/server.cer"
    assert runtime.winrm_trust_certificate_path({}) == "/trust/server.cer"
    assert runtime.winrm_trust_pem_path({}) == "/trust/server.pem"
    assert runtime.parse_winrm_certificate("/trust/server.cer") == "certificate"
    assert runtime.parse_winrm_certificate_bytes(b"raw") == "parsed"
    assert runtime.read_winrm_trust_metadata({}) == {"source": "test"}
    assert runtime.validate_winrm_certificate("certificate", {}) == {"status": "ready"}
    assert runtime.winrm_certificate_response_metadata("certificate", {}, "DER") == {
        "status": "ready"
    }
    assert any(call[0] == "validate" for call in calls)


def test_winrm_trust_runtime_resolves_mutable_paths_and_callbacks():
    calls = []
    providers = {
        "_resolve_trust_root_impl": lambda path, **_kwargs: path,
        "OPS_WINRM_TRUST_PATH": "/first",
        "os": SimpleNamespace(path=SimpleNamespace(realpath=lambda path: path, abspath=lambda path: path)),
        "WinRMTrustError": RuntimeError,
        "WINRM_CERTIFICATE_INVALID_MESSAGE": "invalid",
        "_refresh_winrm_trust_store_impl": lambda hosts, root, **kwargs: calls.append(
            (hosts, root, kwargs)
        ) or {"host": {"status": "missing"}},
        "_winrm_trust_root": lambda: providers["OPS_WINRM_TRUST_PATH"],
        "winrm_trust_ref_for_host": lambda host: "ref",
        "inspect_winrm_trust": lambda host: {"status": "missing"},
        "_sanitize_log_value": str,
        "logging": None,
    }
    runtime = create_winrm_trust_runtime(providers)
    providers["OPS_WINRM_TRUST_PATH"] = "/second"

    assert runtime.refresh_winrm_trust_store([{"name": "host"}]) == {
        "host": {"status": "missing"}
    }
    assert calls[0][1] == "/second"


def test_winrm_trust_runtime_forwards_http_status_mapping():
    providers = {
        "_trust_http_status_impl": lambda code: {"known": 422}.get(code, 400),
    }
    runtime = create_winrm_trust_runtime(providers)

    assert runtime.trust_http_status("known") == 422
    assert runtime.trust_http_status("other") == 400


def test_winrm_trust_runtime_forwards_error_payload_dependencies():
    calls = []
    providers = {
        "_build_winrm_trust_error_payload_impl": lambda *args, **kwargs: calls.append(
            (args, kwargs)
        ) or {"code": "WINRM_TRUST_INVALID"},
        "_request_id": "request-id",
        "WINRM_TRUST_ERROR_MESSAGES": {"WINRM_TRUST_INVALID": "invalid"},
    }
    runtime = create_winrm_trust_runtime(providers)

    assert runtime.winrm_trust_error_payload("host", "WINRM_TRUST_INVALID") == {
        "code": "WINRM_TRUST_INVALID"
    }
    assert calls == [
        (
            ("host", "WINRM_TRUST_INVALID"),
            {
                "request_id": "request-id",
                "trust_error_messages": providers["WINRM_TRUST_ERROR_MESSAGES"],
            },
        )
    ]
