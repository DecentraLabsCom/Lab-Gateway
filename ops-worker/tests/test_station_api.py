from flask import Flask

import pytest

from station_api_blueprint import create_station_api_blueprint
from station_errors import StationAuthenticationFailed, StationTrustRequired, StationUnreachable


@pytest.fixture
def station_api():
    handlers = {
        "find_host": lambda name: {"name": name, "address": "192.0.2.12"} if name == "linux-1" else None,
        "run_station_command": lambda host, command, args, **kwargs: {"id": kwargs["request_id"], "command": command, "args": args, "exitCode": 0},
        "generate_ssh_credential": lambda ref, **kwargs: {"credentialRef": ref, "username": kwargs["username"]},
        "public_ssh_credential": lambda ref: {"credentialRef": ref, "publicKey": "ssh-ed25519 public"} if ref == "cred-1" else None,
        "delete_ssh_credential": lambda ref: ref == "cred-1",
        "probe_ssh_host_key": lambda host: {"algorithm": "ssh-ed25519", "fingerprint": "SHA256:preview"},
        "confirm_ssh_host_key": lambda host, fingerprint: {"status": "ready", "fingerprint": fingerprint},
        "ssh_trust_status": lambda host: {"status": "ready"},
        "delete_ssh_trust": lambda host: True,
        "probe_station": lambda host: {"reachable": True, "transport": "ssh"},
    }
    app = Flask(__name__)
    app.register_blueprint(create_station_api_blueprint(
        find_host=lambda *args, **kwargs: handlers["find_host"](*args, **kwargs),
        run_station_command=lambda *args, **kwargs: handlers["run_station_command"](*args, **kwargs),
        generate_ssh_credential=lambda *args, **kwargs: handlers["generate_ssh_credential"](*args, **kwargs),
        public_ssh_credential=lambda *args, **kwargs: handlers["public_ssh_credential"](*args, **kwargs),
        delete_ssh_credential=lambda *args, **kwargs: handlers["delete_ssh_credential"](*args, **kwargs),
        probe_ssh_host_key=lambda *args, **kwargs: handlers["probe_ssh_host_key"](*args, **kwargs),
        confirm_ssh_host_key=lambda *args, **kwargs: handlers["confirm_ssh_host_key"](*args, **kwargs),
        ssh_trust_status=lambda *args, **kwargs: handlers["ssh_trust_status"](*args, **kwargs),
        delete_ssh_trust=lambda *args, **kwargs: handlers["delete_ssh_trust"](*args, **kwargs),
        probe_station=lambda *args, **kwargs: handlers["probe_station"](*args, **kwargs),
    ))
    app.testing = True
    return app.test_client(), handlers


def test_station_command_calls_transport_and_returns_generated_request_id(station_api):
    client, _ = station_api
    response = client.post("/api/station/command", json={"host": "linux-1", "command": "status-json", "args": []})

    assert response.status_code == 200
    assert response.json["command"] == "status-json"
    assert response.json["args"] == []
    assert response.json["id"]


@pytest.mark.parametrize("payload", [None, [], "not-json"])
def test_station_command_requires_a_json_object(station_api, payload):
    client, _ = station_api
    response = client.post("/api/station/command", json=payload) if payload is not None else client.post("/api/station/command", data="not-json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.parametrize("args", [None, "status-json", {}, 1, ["status-json", 4]])
def test_station_command_rejects_malformed_args_instead_of_coercing(station_api, args):
    client, _ = station_api
    response = client.post("/api/station/command", json={"host": "linux-1", "command": "status-json", "args": args})
    assert response.status_code == 400


def test_station_command_returns_not_found_and_preserves_warning_exit_status(station_api):
    client, handlers = station_api
    missing = client.post("/api/station/command", json={"host": "unknown", "command": "status-json"})
    assert missing.status_code == 404

    handlers["run_station_command"] = lambda *args, **kwargs: {"exitCode": 1, "outcome": "warning"}
    warning = client.post("/api/station/command", json={"host": "linux-1", "command": "prepare-session"})
    assert warning.status_code == 200
    assert warning.json["exitCode"] == 1

    handlers["run_station_command"] = lambda *args, **kwargs: {"exitCode": 2, "outcome": "failure"}
    failure = client.post("/api/station/command", json={"host": "linux-1", "command": "prepare-session"})
    assert failure.status_code == 409


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (StationTrustRequired(), 409, "STATION_TRUST_REQUIRED"),
        (StationAuthenticationFailed(), 401, "STATION_AUTH_FAILED"),
        (StationUnreachable(), 502, "STATION_UNREACHABLE"),
    ],
)
def test_station_error_status_mapping_is_stable(station_api, exception, status, code):
    client, handlers = station_api
    handlers["run_station_command"] = lambda *args, **kwargs: (_ for _ in ()).throw(exception)
    response = client.post("/api/station/command", json={"host": "linux-1", "command": "status-json"})

    assert response.status_code == status
    assert response.json["code"] == code
    assert response.json["requestId"]
    assert response.json["transport"] == "ssh"


def test_credential_and_trust_routes_expose_only_expected_lifecycle(station_api):
    client, _ = station_api
    created = client.post("/api/station/credentials/cred-1", json={})
    public = client.get("/api/station/credentials/cred-1")
    preview = client.post("/api/station/hosts/linux-1/trust/preview")
    confirmed = client.post("/api/station/hosts/linux-1/trust/confirm", json={"fingerprint": "SHA256:preview"})
    status = client.get("/api/station/hosts/linux-1/trust")
    probe = client.post("/api/station/hosts/linux-1/verify")

    assert created.status_code == 201
    assert created.json["username"] == "labstation-ops"
    assert public.status_code == 200 and "privateKey" not in public.json
    assert preview.json["algorithm"] == "ssh-ed25519"
    assert confirmed.status_code == 201 and confirmed.json["status"] == "ready"
    assert status.json["status"] == "ready"
    assert probe.json["reachable"] is True
    assert client.delete("/api/station/credentials/cred-1").json["deleted"] is True
    assert client.delete("/api/station/hosts/linux-1/trust").json["deleted"] is True


def test_credential_and_trust_routes_handle_missing_stations_and_values(station_api):
    client, _ = station_api
    assert client.get("/api/station/credentials/missing").status_code == 404
    assert client.post("/api/station/hosts/missing/trust/preview").status_code == 404
    assert client.post("/api/station/hosts/missing/trust/confirm", json={"fingerprint": "x"}).status_code == 404
    assert client.get("/api/station/hosts/missing/trust").status_code == 404
    assert client.delete("/api/station/hosts/missing/trust").status_code == 404
    assert client.post("/api/station/hosts/missing/verify").status_code == 404


@pytest.mark.parametrize("payload", [[], "bad", 1])
def test_credential_and_trust_mutations_require_object_payloads(station_api, payload):
    client, _ = station_api
    credential = client.post("/api/station/credentials/cred-1", json=payload)
    trust = client.post("/api/station/hosts/linux-1/trust/confirm", json=payload)
    assert credential.status_code == 400
    assert trust.status_code == 400


def test_station_api_routes_require_the_worker_internal_authentication(client):
    response = client.post(
        "/api/station/command",
        json={"host": "untrusted", "command": "status-json"},
        headers={"X-Ops-Internal-Token": ""},
    )

    assert response.status_code == 401
    assert response.json["error"] == "Unauthorized"
