from flask import Flask

import worker
from aas_lab_sync_blueprint import create_aas_lab_sync_blueprint


def _blueprint(**overrides):
    providers = {
        "find_host_by_lab": lambda _lab_id: {"name": "lab-ws-01", "labs": ["lab-1"]},
        "parse_bool": lambda value, default: bool(value) if value is not None else default,
        "poll_heartbeat": lambda _host, **_kwargs: {"heartbeat": {"ready": True}},
        "load_persisted_heartbeat": lambda _lab_id, _host: None,
        "sync_lab": lambda lab_id, _host, _heartbeat: {"synced": True, "labId": lab_id},
        "log_warning": lambda *_args: None,
    }
    providers.update(overrides)
    return create_aas_lab_sync_blueprint(**providers)


def test_aas_lab_sync_blueprint_registers_expected_route():
    app = Flask("aas-lab-sync-blueprint-contract")
    app.register_blueprint(_blueprint())

    rules = [
        rule for rule in app.url_map.iter_rules() if rule.rule == "/aas-admin/lab/<lab_id>/sync"
    ]

    assert len(rules) == 1
    assert rules[0].methods == {"POST", "OPTIONS"}
    assert rules[0].endpoint == "aas_lab_sync.api_aas_sync_lab"


def test_aas_lab_sync_blueprint_forwards_persisted_heartbeat():
    app = Flask("aas-lab-sync-forwarding-contract")
    host = {"name": "lab-ws-01", "labs": ["lab-1"]}
    heartbeat = {"ready": True, "source": "db"}
    calls = []
    app.register_blueprint(
        _blueprint(
            find_host_by_lab=lambda lab_id: calls.append(("find", lab_id)) or host,
            load_persisted_heartbeat=lambda lab_id, value: calls.append(
                ("load", lab_id, value)
            )
            or heartbeat,
            sync_lab=lambda lab_id, value, received_heartbeat: calls.append(
                ("sync", lab_id, value, received_heartbeat)
            )
            or {"synced": True, "labId": lab_id},
        )
    )

    response = app.test_client().post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.get_json() == {"synced": True, "labId": "lab-1"}
    assert calls == [
        ("find", "lab-1"),
        ("load", "lab-1", host),
        ("sync", "lab-1", host, heartbeat),
    ]


def test_aas_lab_sync_blueprint_forwards_requested_poll_and_maps_sync_errors():
    app = Flask("aas-lab-sync-poll-contract")
    host = {"name": "lab-ws-01", "labs": ["lab-1"]}
    calls = []
    app.register_blueprint(
        _blueprint(
            find_host_by_lab=lambda _lab_id: host,
            poll_heartbeat=lambda value, **kwargs: calls.append(("poll", value, kwargs))
            or {"heartbeat": {"ready": True, "source": "poll"}},
            sync_lab=lambda lab_id, value, heartbeat: calls.append(
                ("sync", lab_id, value, heartbeat)
            )
            or {"error": "AAS synchronization failed", "labId": lab_id},
        )
    )

    response = app.test_client().post(
        "/aas-admin/lab/lab-1/sync", json={"includeHeartbeat": True}
    )

    assert response.status_code == 502
    assert response.get_json() == {
        "detail": "AAS synchronization failed",
        "error": "AAS synchronization failed",
        "labId": "lab-1",
    }
    assert calls == [
        ("poll", host, {"include_events": False}),
        ("sync", "lab-1", host, {"ready": True, "source": "poll"}),
    ]


def test_worker_aas_lab_sync_route_is_owned_by_the_blueprint(monkeypatch):
    host = {"name": "lab-ws-01", "address": "192.168.1.50", "labs": ["lab-1"]}
    monkeypatch.setattr(worker, "HOSTS", worker.HostRegistry({"hosts": [host]}))
    monkeypatch.setattr(worker, "DB_ENGINE", None)
    monkeypatch.setattr(
        worker.aas_generator,
        "sync_lab_to_basyx",
        lambda lab_id, received_host, heartbeat: {
            "synced": True,
            "labId": lab_id,
            "heartbeat": heartbeat,
        },
    )

    rules = [
        rule
        for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/aas-admin/lab/<lab_id>/sync"
    ]
    assert len(rules) == 1
    assert rules[0].endpoint == "aas_lab_sync.api_aas_sync_lab"
    assert callable(worker.api_aas_sync_lab)

    response = worker.APP.test_client().post("/aas-admin/lab/lab-1/sync")

    assert response.status_code == 200
    assert response.json == {
        "synced": True,
        "labId": "lab-1",
        "heartbeat": None,
    }
