from flask import Flask

import worker
from winrm_trust_mutation_blueprint import create_winrm_trust_mutation_blueprint


def _trust_error_payload(host_name, code):
    return {"host": host_name, "code": code}


def _blueprint(**overrides):
    providers = {
        "find_host": lambda _name: {"name": "lab-ws-01", "address": "192.168.1.50"},
        "request_value": lambda _name: "A" * 64,
        "normalize_trust_ref": lambda value: str(value).strip().lower(),
        "trust_ref_for_host": lambda _host: "pc-siemens",
        "read_certificate_upload": lambda: b"certificate",
        "parse_certificate": lambda _raw: object(),
        "validate_certificate": lambda _certificate, _host: {"fingerprintSha256": "A" * 64},
        "store_trust": lambda _host, _certificate: {"configured": True},
        "delete_trust": lambda _host: None,
        "inspect_trust": lambda _host: {"configured": False},
        "request_id": lambda: "request-1",
        "sanitize_log_value": lambda value: str(value),
        "log_info": lambda *_args: None,
        "log_warning": lambda *_args: None,
        "trust_error_type": worker.WinRMTrustError,
        "trust_error_payload": _trust_error_payload,
        "trust_http_status": lambda _code: 400,
        "fingerprint_confirmation_required_message": "fingerprint required",
        "fingerprint_mismatch_message": "fingerprint mismatch",
        "trust_ref_mismatch_message": "trust ref mismatch",
        "internal_error_response": lambda message, exc: ({"error": message}, 500),
    }
    providers.update(overrides)
    return create_winrm_trust_mutation_blueprint(**providers)


def test_winrm_trust_mutation_blueprint_registers_put_and_delete_without_duplication():
    app = Flask("winrm-trust-mutation-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust"
    ]

    assert len(rules) == 2
    by_method = {next(iter(rule.methods - {"OPTIONS"})): rule for rule in rules}
    assert by_method["PUT"].methods == {"PUT", "OPTIONS"}
    assert by_method["PUT"].endpoint == "winrm_trust_mutation.api_save_winrm_trust"
    assert by_method["DELETE"].methods == {"DELETE", "OPTIONS"}
    assert by_method["DELETE"].endpoint == "winrm_trust_mutation.api_delete_winrm_trust"


def test_winrm_trust_mutation_blueprint_forwards_put_certificate_contract():
    app = Flask("winrm-trust-put-forwarding-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    certificate = object()
    calls = []
    app.register_blueprint(
        _blueprint(
            find_host=lambda _name: host,
            request_value=lambda name: {"fingerprintSha256": "A" * 64, "trustRef": "pc-siemens"}.get(name, ""),
            read_certificate_upload=lambda: calls.append(("read",)) or b"certificate",
            parse_certificate=lambda raw: calls.append(("parse", raw)) or certificate,
            validate_certificate=lambda value, received_host: calls.append(
                ("validate", value, received_host)
            )
            or {"fingerprintSha256": "A" * 64},
            store_trust=lambda received_host, value: calls.append(
                ("store", received_host, value)
            )
            or {"configured": True},
        )
    )

    response = app.test_client().put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json={"fingerprintSha256": "A" * 64, "trustRef": "pc-siemens"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "requestId": "request-1",
        "saved": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": {"configured": True},
    }
    assert calls == [
        ("read",),
        ("parse", b"certificate"),
        ("validate", certificate, host),
        ("store", host, certificate),
    ]


def test_winrm_trust_mutation_blueprint_forwards_delete_contract():
    app = Flask("winrm-trust-delete-forwarding-contract")
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    calls = []
    app.register_blueprint(
        _blueprint(
            find_host=lambda _name: host,
            delete_trust=lambda value: calls.append(("delete", value)),
            inspect_trust=lambda value: calls.append(("inspect", value)) or {"configured": False},
        )
    )

    response = app.test_client().delete("/api/hosts/lab-ws-01/winrm-trust")

    assert response.status_code == 200
    assert response.get_json() == {
        "requestId": "request-1",
        "deleted": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "trust": {"configured": False},
    }
    assert calls == [("delete", host), ("inspect", host)]


def test_worker_winrm_trust_mutations_are_owned_by_the_blueprint(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50"}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "_winrm_trust_request_value", lambda name: "A" * 64 if name == "fingerprintSha256" else "")
    monkeypatch.setattr(worker, "_read_winrm_certificate_upload", lambda: b"certificate")
    monkeypatch.setattr(worker, "_parse_winrm_certificate_bytes", lambda _raw: object())
    monkeypatch.setattr(
        worker,
        "_validate_winrm_certificate",
        lambda _certificate, _host: {"fingerprintSha256": "A" * 64},
    )
    monkeypatch.setattr(
        worker,
        "_store_winrm_trust_certificate",
        lambda _host, _certificate: {"configured": True},
    )
    monkeypatch.setattr(worker, "_delete_winrm_trust_certificate", lambda _host: None)
    monkeypatch.setattr(worker, "inspect_winrm_trust", lambda _host: {"configured": False})

    rules = [
        rule
        for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/hosts/<host_name>/winrm-trust"
        and ("PUT" in rule.methods or "DELETE" in rule.methods)
    ]
    assert len(rules) == 2
    assert {rule.endpoint for rule in rules} == {
        "winrm_trust_mutation.api_save_winrm_trust",
        "winrm_trust_mutation.api_delete_winrm_trust",
    }
    assert callable(worker.api_save_winrm_trust)
    assert callable(worker.api_delete_winrm_trust)

    client = worker.APP.test_client()
    put_response = client.put(
        "/api/hosts/lab-ws-01/winrm-trust",
        json={"fingerprintSha256": "A" * 64},
    )
    delete_response = client.delete("/api/hosts/lab-ws-01/winrm-trust")

    assert put_response.status_code == 200
    assert delete_response.status_code == 200
