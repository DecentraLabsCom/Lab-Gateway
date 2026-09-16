from flask import Flask

import worker
from winrm_trust_preview_blueprint import create_winrm_trust_preview_blueprint


def test_winrm_trust_preview_blueprint_preserves_valid_preview_contract():
    app = Flask("winrm-trust-preview-blueprint-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    certificate = object()
    calls = []

    app.register_blueprint(
        create_winrm_trust_preview_blueprint(
            find_host=lambda value: host if value == "lab-ws-01" else None,
            read_certificate_upload=lambda: b"-----BEGIN CERTIFICATE-----",
            parse_certificate=lambda raw: calls.append(("parse", raw)) or certificate,
            response_metadata=lambda value, host_arg, input_format: calls.append(
                ("metadata", value, host_arg, input_format)
            ) or {"fingerprintSha256": "A" * 64, "format": input_format},
            validate_certificate=lambda value, host_arg: calls.append(
                ("validate", value, host_arg)
            ),
            request_id=lambda: "trust-preview-blueprint-1",
            trust_error_type=RuntimeError,
            trust_error_payload=lambda host_name, code: {
                "host": host_name,
                "code": code,
            },
            trust_http_status=lambda _code: 422,
            internal_error_response=lambda _message, _exc: ({"error": "internal"}, 500),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust/preview"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "winrm_trust_preview.api_preview_winrm_trust"

    response = app.test_client().post(
        "/api/hosts/lab-ws-01/winrm-trust/preview"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "requestId": "trust-preview-blueprint-1",
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "preview": {
            "fingerprintSha256": "A" * 64,
            "format": "PEM",
            "valid": True,
        },
    }
    assert calls[0] == ("parse", b"-----BEGIN CERTIFICATE-----")
    assert calls[1] == ("metadata", certificate, host, "PEM")
    assert calls[2] == ("validate", certificate, host)


def test_worker_winrm_trust_preview_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust/preview"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "winrm_trust_preview.api_preview_winrm_trust"


def test_worker_winrm_trust_preview_blueprint_resolves_runtime_dependencies(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    certificate = object()
    calls = []
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"der")
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda raw: calls.append(("parse", raw)) or certificate)
    monkeypatch.setattr(
        worker,
        "_winrm_certificate_response_metadata",
        lambda value, host_arg, input_format: calls.append(
            ("metadata", value, host_arg, input_format)
        ) or {"format": input_format},
    )
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        lambda value, host_arg: calls.append(("validate", value, host_arg)),
    )
    monkeypatch.setattr(worker, "_request_id", lambda: "trust-preview-blueprint-2")

    response = worker.APP.test_client().post(
        "/api/hosts/lab-ws-01/winrm-trust/preview"
    )

    assert response.status_code == 200
    payload = response.json
    assert payload is not None
    assert payload["requestId"] == "trust-preview-blueprint-2"
    assert payload["preview"]["format"] == "DER"
    assert calls == [
        ("parse", b"der"),
        ("metadata", certificate, host, "DER"),
        ("validate", certificate, host),
    ]
