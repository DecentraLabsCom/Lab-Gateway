from flask import Flask

import worker
from aas_sync_blueprint import create_aas_sync_blueprint


def test_aas_sync_blueprint_registers_the_expected_route():
    app = Flask("aas-sync-blueprint-contract")
    app.register_blueprint(
        create_aas_sync_blueprint(
            find_host=lambda _name: None,
            resolve_lab_ids_for_host=lambda _host: [],
            sync_lab=lambda _lab_id, _host: {},
            log_failure=lambda *_args: None,
        )
    )

    rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/api/aas-sync"]

    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "aas_sync.api_aas_sync"


def test_aas_sync_blueprint_forwards_host_and_each_lab():
    app = Flask("aas-sync-forwarding-contract")
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "labs": [1, "2"],
    }
    calls = []
    app.register_blueprint(
        create_aas_sync_blueprint(
            find_host=lambda name: calls.append(("find", name)) or host,
            resolve_lab_ids_for_host=lambda _host: [1, "2"],
            sync_lab=lambda lab_id, host_arg: calls.append(("sync", lab_id, host_arg))
            or {"synced": True},
            log_failure=lambda *_args: None,
        )
    )

    response = app.test_client().post("/api/aas-sync", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.get_json() == {
        "host": "lab-ws-01",
        "labs": [
            {"labId": "1", "synced": True},
            {"labId": "2", "synced": True},
        ],
    }
    assert calls == [
        ("find", "lab-ws-01"),
        ("sync", "1", host),
        ("sync", "2", host),
    ]


def test_aas_sync_blueprint_preserves_missing_host_and_lab_error_contracts():
    app = Flask("aas-sync-error-contract")
    failures = []
    app.register_blueprint(
        create_aas_sync_blueprint(
            find_host=lambda name: {"name": name, "labs": [1]} if name == "known" else None,
            resolve_lab_ids_for_host=lambda _host: [1],
            sync_lab=lambda _lab_id, _host: (_ for _ in ()).throw(
                RuntimeError("secret BaSyx details")
            ),
            log_failure=lambda *args: failures.append(args),
        )
    )

    missing_payload = app.test_client().post("/api/aas-sync", json={})
    unknown_host = app.test_client().post("/api/aas-sync", json={"host": "missing"})
    lab_error = app.test_client().post("/api/aas-sync", json={"host": "known"})

    assert missing_payload.status_code == 400
    assert missing_payload.get_json() == {"error": "host is required"}
    assert unknown_host.status_code == 404
    assert unknown_host.get_json() == {"error": "host 'missing' not found in config"}
    assert lab_error.status_code == 200
    assert lab_error.get_json() == {
        "host": "known",
        "labs": [{"labId": "1", "error": "AAS synchronization failed"}],
    }
    assert failures == [("AAS sync failed for lab %s", 1)]
    assert "secret BaSyx details" not in lab_error.get_data(as_text=True)


def test_worker_aas_sync_route_is_owned_by_the_blueprint(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50", "labs": [1]}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "resolve_lab_ids_for_host", lambda _host: [1])
    monkeypatch.setattr(
        worker.aas_generator,
        "sync_lab_to_basyx",
        lambda lab_id, host_arg: {"synced": True, "labId": lab_id},
    )

    rules = [rule for rule in worker.APP.url_map.iter_rules() if rule.rule == "/api/aas-sync"]
    assert len(rules) == 1
    assert rules[0].endpoint == "aas_sync.api_aas_sync"

    response = worker.APP.test_client().post("/api/aas-sync", json={"host": "lab-ws-01"})

    assert response.status_code == 200
    assert response.json == {
        "host": "lab-ws-01",
        "labs": [{"labId": "1", "synced": True}],
    }
