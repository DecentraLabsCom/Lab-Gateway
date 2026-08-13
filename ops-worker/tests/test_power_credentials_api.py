import json
import os
import sys

from cryptography.fernet import Fernet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker
from power.credentials import PowerCredentialStore
from power.service import PowerRuntime


def build_store(tmp_path):
    return PowerCredentialStore(str(tmp_path / "power-credentials.json"), Fernet.generate_key().decode())


def test_power_credentials_api_lists_metadata_and_never_returns_secrets(client, tmp_path, monkeypatch):
    store = build_store(tmp_path)
    store.put(
        "netio-lab-01",
        "netio-http-basic",
        {"username": "netio", "password": "super-secret"},
    )
    monkeypatch.setitem(worker.APP.extensions, "power_credential_store", store)

    response = client.get("/api/power/credentials")

    assert response.status_code == 200
    assert response.json == {
        "success": True,
        "credentials": [{"credentialRef": "netio-lab-01", "type": "netio-http-basic"}],
    }
    assert "super-secret" not in response.get_data(as_text=True)


def test_power_credentials_api_creates_and_rotates_an_encrypted_credential(client, tmp_path, monkeypatch):
    store = build_store(tmp_path)
    monkeypatch.setitem(worker.APP.extensions, "power_credential_store", store)

    created = client.post(
        "/api/power/credentials",
        json={
            "credentialRef": "netio-lab-01",
            "type": "netio-http-basic",
            "credentials": {"username": "netio", "password": "first-secret"},
        },
    )

    assert created.status_code == 201
    assert created.json == {
        "success": True,
        "credential": {"credentialRef": "netio-lab-01", "type": "netio-http-basic"},
        "rotated": False,
        "runtimeReloaded": True,
    }
    assert "first-secret" not in created.get_data(as_text=True)
    assert store.get("netio-lab-01") == {"username": "netio", "password": "first-secret"}

    duplicate = client.post(
        "/api/power/credentials",
        json={
            "credentialRef": "netio-lab-01",
            "type": "netio-http-basic",
            "credentials": {"username": "netio", "password": "second-secret"},
        },
    )
    assert duplicate.status_code == 409
    assert "second-secret" not in duplicate.get_data(as_text=True)

    rotated = client.post(
        "/api/power/credentials",
        json={
            "credentialRef": "netio-lab-01",
            "type": "netio-http-basic",
            "credentials": {"username": "netio", "password": "second-secret"},
            "overwrite": True,
        },
    )
    assert rotated.status_code == 200
    assert rotated.json["rotated"] is True
    assert store.get("netio-lab-01")["password"] == "second-secret"
    assert "second-secret" not in rotated.get_data(as_text=True)


def test_power_credential_rotation_rebuilds_configured_netio_driver(client, tmp_path, monkeypatch):
    store = build_store(tmp_path)
    store.put("netio-lab-01-http", "netio-http-basic", {"username": "old", "password": "old-secret"})
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(
        json.dumps({
            "controllers": [{
                "id": "netio-lab-01",
                "name": "NETIO Lab 01",
                "driver": "netio-json",
                "host": "127.0.0.1",
                "port": 80,
                "credentialRef": "netio-lab-01-http",
            }],
            "outlets": [{"controllerId": "netio-lab-01", "outlet": "1"}],
            "policies": [],
        }),
        encoding="utf-8",
    )
    runtime = PowerRuntime.from_path(str(config_path), credential_resolver=store.get)
    monkeypatch.setitem(worker.APP.extensions, "power_credential_store", store)
    monkeypatch.setitem(worker.APP.extensions, "power_runtime", runtime)

    response = client.post(
        "/api/power/credentials",
        json={
            "credentialRef": "netio-lab-01-http",
            "type": "netio-http-basic",
            "credentials": {"username": "new", "password": "new-secret"},
            "overwrite": True,
        },
    )

    assert response.status_code == 200
    assert response.json["runtimeReloaded"] is True
    assert runtime.registry.get("netio-lab-01").driver.auth == ("new", "new-secret")


def test_power_credentials_api_rejects_invalid_payload_without_changing_store(client, tmp_path, monkeypatch):
    store = build_store(tmp_path)
    store.put("pdu-1", "snmpv2c", {"version": "v2c", "community": "private"})
    monkeypatch.setitem(worker.APP.extensions, "power_credential_store", store)

    response = client.post(
        "/api/power/credentials",
        json={
            "credentialRef": "pdu-1",
            "type": "snmpv2c",
            "credentials": {"version": "v2c", "community": ""},
            "overwrite": True,
        },
    )

    assert response.status_code == 400
    assert response.json["error"] == "Power credential is invalid"
    assert store.get("pdu-1") == {"version": "v2c", "community": "private"}


def test_power_credentials_api_requires_internal_auth(client, tmp_path, monkeypatch):
    monkeypatch.setitem(worker.APP.extensions, "power_credential_store", build_store(tmp_path))

    response = client.get(
        "/api/power/credentials",
        headers={worker.OPS_INTERNAL_AUTH_HEADER: ""},
    )

    assert response.status_code == 401
    assert "credentials" not in response.get_data(as_text=True).lower()
