import base64
import json
import socket
import threading
import time
from io import StringIO

import paramiko
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import station_ssh_trust
import transports.ssh as ssh_module
from station_errors import StationAuthenticationFailed, StationCommandRejected, StationTrustMismatch, StationUnreachable
from transports.ssh import SshTransport


class _GatewayClient(paramiko.ServerInterface):
    def __init__(self, expected_username, expected_key):
        self.expected_username = expected_username
        self.expected_key = expected_key
        self.exec_command = None
        self.exec_requested = threading.Event()

    def get_allowed_auths(self, username):
        return "publickey"

    def check_auth_publickey(self, username, key):
        if username == self.expected_username and key.asbytes() == self.expected_key.asbytes():
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.exec_command = command.decode("utf-8") if isinstance(command, bytes) else command
        self.exec_requested.set()
        return True


def _new_ed25519_material():
    private = Ed25519PrivateKey.generate()
    encoded = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode("ascii")
    return paramiko.Ed25519Key.from_private_key(StringIO(encoded)), encoded


def _new_ed25519_key():
    return _new_ed25519_material()[0]


def _run_server(monkeypatch, *, handler=None, expected_client_key=None, wrong_host_key=None, request_count=1):
    host_key = wrong_host_key or _new_ed25519_key()
    client_key, client_private = _new_ed25519_material()
    expected_client_key = expected_client_key or client_key
    host_fingerprint = station_ssh_trust._fingerprint(host_key)
    monkeypatch.setattr(
        ssh_module,
        "load_ssh_credential",
        lambda ref: {"username": "labstation-ops", "privateKey": client_private, "publicKey": client_key.get_base64()},
    )
    monkeypatch.setattr(
        ssh_module,
        "load_confirmed_ssh_host_key",
        lambda host: ("ssh-ed25519", base64.b64encode(host_key.asbytes()).decode("ascii"), host_fingerprint),
    )

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(request_count)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    received = []
    errors = []

    def serve():
        try:
            for _ in range(request_count):
                connection = None
                transport = None
                channel = None
                auth = _GatewayClient("labstation-ops", expected_client_key)
                try:
                    connection, _ = listener.accept()
                    transport = paramiko.Transport(connection)
                    transport.add_server_key(host_key)
                    transport.start_server(server=auth)
                    channel = transport.accept(timeout=5)
                    if channel is None:
                        return
                    deadline = time.monotonic() + 5
                    request = bytearray()
                    while time.monotonic() < deadline:
                        data = channel.recv(65536)
                        if not data:
                            break
                        request.extend(data)
                    envelope = json.loads(request.decode("utf-8"))
                    received.append({"command": auth.exec_command, "payload": envelope})
                    response = handler(envelope) if handler else {
                        "id": envelope.get("id", "server-id"),
                        "command": envelope.get("command", "artifact.read"),
                        "completedAt": "2026-10-06T12:00:00Z",
                        "success": True,
                        "exitCode": 0,
                        "outcome": "success",
                        "message": "success",
                        "stdout": "{\"contractVersion\":\"3.0.0\",\"host\":\"linux-1\"}",
                        "stderr": "",
                        "durationMs": 1,
                        "metadata": {},
                    }
                    channel.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    channel.send_exit_status(0)
                finally:
                    if channel:
                        channel.close()
                    if transport:
                        transport.close()
                    if connection:
                        connection.close()
        except Exception as exc:  # surfaced in the test thread after the network path is closed
            errors.append(exc)
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    host = {"name": "linux-1", "address": "127.0.0.1", "management": {"transport": "ssh", "port": port, "credentialRef": "cred-1", "trustRef": "linux-1"}}
    return SshTransport(connect_timeout=2, command_timeout=3), host, thread, received, errors


def _finish(thread, errors):
    thread.join(timeout=6)
    assert not thread.is_alive(), "local SSH server did not finish"
    assert not errors, f"local SSH server failed: {errors!r}"


def test_real_ssh_handshake_dispatches_only_a_structured_request_and_normalizes_result(monkeypatch):
    transport, host, thread, received, errors = _run_server(
        monkeypatch,
        handler=lambda envelope: {
            "id": envelope["id"], "command": envelope["command"], "exitCode": 1,
            "stdout": "preparation complete", "stderr": "notification unavailable", "metadata": {"releasedSessions": 1},
            "completedAt": "2026-10-06T12:00:00Z", "success": True, "outcome": "warning",
            "message": "preparation complete", "durationMs": 8,
        },
    )

    result = transport.execute(host, "prepare-session", ["--guard-grace=0"], request_id="request-77")

    _finish(thread, errors)
    assert received[0]["command"] == "station"
    assert received[0]["payload"] == {
        "schemaVersion": 1, "id": "request-77", "operation": "execute",
        "command": "prepare-session", "args": ["--guard-grace=0"],
    }
    assert result["id"] == "request-77"
    assert result["outcome"] == "warning"
    assert result["success"] is True
    assert result["metadata"]["releasedSessions"] == 1
    assert result["completedAt"] == "2026-10-06T12:00:00Z"


@pytest.mark.parametrize(
    "response",
    [
        {"id": "another-request", "command": "prepare-session", "exitCode": 0},
        {"id": "request-78", "command": "release-session", "exitCode": 0},
        {"id": "request-78", "command": "prepare-session"},
        {"id": "request-78", "command": "prepare-session", "exitCode": True},
        {"id": "request-78", "command": "prepare-session", "exitCode": "0"},
    ],
)
def test_real_ssh_rejects_uncorrelated_or_malformed_command_results(monkeypatch, response):
    transport, host, thread, _received, errors = _run_server(
        monkeypatch,
        handler=lambda _envelope: response,
    )

    with pytest.raises(StationUnreachable):
        transport.execute(host, "prepare-session", [], request_id="request-78")

    _finish(thread, errors)


def test_real_ssh_identity_probe_requires_station_contract_v3(monkeypatch):
    transport, host, thread, received, errors = _run_server(monkeypatch)

    result = transport.probe(host)

    _finish(thread, errors)
    assert result["reachable"] is True
    assert result["transport"] == "ssh"
    assert result["identity"]["contractVersion"] == "3.0.0"
    assert received[0]["payload"]["command"] == "identity"


def test_real_ssh_negotiates_v2_and_sends_stable_lease_envelope(monkeypatch):
    operation_id = "prepare-reservation-19"
    issued_at = "2026-10-08T09:59:00Z"
    execute_before = "2026-10-08T10:04:00Z"

    def handler(envelope):
        operation = envelope["operation"]
        if envelope.get("command") == "identity":
            stdout = json.dumps({
                "contractVersion": "3.0.0", "dispatcherVersions": [1, 2],
                "capabilities": ["reservation-lease-v1", "operation-status-v1"],
            })
            exit_code, outcome = 0, "success"
            command = "identity"
        elif operation == "operation.status":
            stdout = json.dumps({"operationId": operation_id, "state": "not-found"})
            exit_code, outcome = 1, "warning"
            command = "operation.status"
        else:
            stdout = "prepared"
            exit_code, outcome = 0, "success"
            command = "prepare-session"
        return {
            "id": envelope["id"], "command": command, "completedAt": "2026-10-08T10:00:00Z",
            "success": exit_code < 2, "exitCode": exit_code, "outcome": outcome,
            "message": "completed", "stdout": stdout, "stderr": "", "durationMs": 3, "metadata": {},
        }

    transport, host, thread, received, errors = _run_server(
        monkeypatch, handler=handler, request_count=3,
    )
    dispatcher_request = {
        "requestId": operation_id,
        "issuedAt": issued_at,
        "executeBefore": execute_before,
        "timeoutSeconds": 150,
        "context": {
            "kind": "reservation", "labId": "42", "reservationKey": "reservation-19",
            "leaseId": "lease-19", "notBefore": issued_at, "expiresAt": "2026-10-08T11:00:00Z",
        },
    }

    result = transport.execute(
        host, "prepare-session", ["--guard-grace=0"], dispatcher_request=dispatcher_request,
    )

    _finish(thread, errors)
    assert [item["payload"]["operation"] for item in received] == ["execute", "operation.status", "execute"]
    assert received[0]["payload"]["command"] == "identity"
    assert received[2]["payload"] == {
        "schemaVersion": 2, "id": operation_id, "operation": "execute", "command": "prepare-session",
        "args": ["--guard-grace=0"], "issuedAt": issued_at, "executeBefore": execute_before,
        "context": dispatcher_request["context"],
    }
    assert result["id"] == operation_id
    assert result["exitCode"] == 0


def test_v2_timeout_reconciles_stored_result_without_reissuing_lifecycle(monkeypatch):
    transport = SshTransport()
    operation_id = "prepare-reconcile-19"
    issued_at = "2026-10-08T09:59:00Z"
    execute_before = "2026-10-08T10:04:00Z"
    host = {"name": "linux-reconcile", "address": "127.0.0.1"}
    requests = []
    status_count = 0

    def dispatch(_host, envelope, *, timeout_seconds=None):
        nonlocal status_count
        requests.append(envelope)
        operation = envelope["operation"]
        command = envelope.get("command") or operation
        stdout = ""
        exit_code = 0
        outcome = "success"
        metadata = {}
        if command == "identity":
            stdout = json.dumps({
                "dispatcherVersions": [1, 2],
                "capabilities": ["reservation-lease-v1"],
            })
        elif operation == "operation.status":
            status_count += 1
            if status_count == 1:
                stdout = json.dumps({"operationId": operation_id, "state": "not-found"})
                exit_code, outcome = 1, "warning"
            else:
                stored_result = {
                    "id": operation_id, "command": "prepare-session", "completedAt": "2026-10-08T10:00:03Z",
                    "success": True, "exitCode": 0, "outcome": "success", "message": "prepared",
                    "stdout": "prepared", "stderr": "", "durationMs": 3000, "metadata": {"lease": {"generation": 1}},
                }
                stdout = json.dumps({"operationId": operation_id, "state": "completed", "result": stored_result})
                metadata = {"operationId": operation_id, "state": "completed"}
        elif operation == "execute":
            raise StationUnreachable("simulated SSH timeout after request delivery")
        return {
            "id": envelope["id"], "command": command, "completedAt": "2026-10-08T10:00:00Z",
            "success": exit_code < 2, "exitCode": exit_code, "outcome": outcome,
            "message": "reconciled", "stdout": stdout, "stderr": "", "durationMs": 1, "metadata": metadata,
        }

    monkeypatch.setattr(transport, "_dispatch", dispatch)
    dispatcher_request = {
        "requestId": operation_id, "issuedAt": issued_at, "executeBefore": execute_before,
        "context": {"kind": "reservation", "labId": "42", "reservationKey": "reservation-19", "leaseId": "lease-19", "notBefore": issued_at, "expiresAt": "2026-10-08T11:00:00Z"},
    }

    result = transport.execute(host, "prepare-session", [], dispatcher_request=dispatcher_request)

    assert [request["operation"] for request in requests] == ["execute", "operation.status", "execute", "operation.status"]
    assert sum(request.get("command") == "prepare-session" for request in requests) == 1
    assert result["id"] == operation_id
    assert result["metadata"]["lease"]["generation"] == 1


def test_v2_refuses_downgrade_when_station_does_not_advertise_lease_capability(monkeypatch):
    transport = SshTransport()
    requests = []

    def dispatch(_host, envelope, *, timeout_seconds=None):
        requests.append(envelope)
        return {
            "id": envelope["id"], "command": "identity", "completedAt": "2026-10-08T10:00:00Z",
            "success": True, "exitCode": 0, "outcome": "success", "message": "identity",
            "stdout": json.dumps({"dispatcherVersions": [1], "capabilities": []}),
            "stderr": "", "durationMs": 1, "metadata": {},
        }

    monkeypatch.setattr(transport, "_dispatch", dispatch)
    request = {
        "requestId": "prepare-no-downgrade", "issuedAt": "2026-10-08T09:59:00Z",
        "executeBefore": "2026-10-08T10:04:00Z",
        "context": {"kind": "reservation", "labId": "42", "reservationKey": "reservation-19", "leaseId": "lease-19", "notBefore": "2026-10-08T09:59:00Z", "expiresAt": "2026-10-08T11:00:00Z"},
    }

    with pytest.raises(StationUnreachable, match="does not support"):
        transport.execute({"address": "127.0.0.1"}, "prepare-session", [], dispatcher_request=request)
    assert len(requests) == 1
    assert requests[0]["command"] == "identity"


def test_operation_status_surfaces_recovery_required_result(monkeypatch):
    transport = SshTransport()
    operation_id = "release-recovery-19"
    stored_result = {
        "id": operation_id, "command": "release-session", "completedAt": "2026-10-08T10:00:03Z",
        "success": False, "exitCode": 2, "outcome": "failure", "message": "operator reconciliation required",
        "stdout": "", "stderr": "operator reconciliation required", "durationMs": 3000,
        "metadata": {"code": "STATION_OPERATION_RECOVERY_REQUIRED"},
    }

    def dispatch(_host, envelope, *, timeout_seconds=None):
        return {
            "id": envelope["id"], "command": "operation.status", "completedAt": "2026-10-08T10:00:04Z",
            "success": True, "exitCode": 0, "outcome": "success", "message": "recovery required",
            "stdout": json.dumps({"operationId": operation_id, "state": "recovery-required", "result": stored_result}),
            "stderr": "", "durationMs": 1, "metadata": {"operationId": operation_id, "state": "recovery-required"},
        }

    monkeypatch.setattr(transport, "_dispatch", dispatch)
    result = transport._operation_status({"address": "127.0.0.1"}, operation_id, "release-session")

    assert result == stored_result


def test_real_ssh_secret_enrollment_keeps_secret_out_of_the_response(monkeypatch):
    secret = "0123456789abcdef0123456789abcdef"
    transport, host, thread, received, errors = _run_server(
        monkeypatch,
        handler=lambda envelope: {
            "id": envelope["id"], "command": "secret.set", "completedAt": "2026-10-06T12:00:00Z",
            "success": True, "exitCode": 0, "outcome": "success", "message": "configured",
            "stdout": "configured", "stderr": "", "durationMs": 1,
            "metadata": {"secretId": envelope["secretId"]},
        },
    )

    result = transport.write_secret(host, "fmu-internal-token", secret)

    _finish(thread, errors)
    assert received[0]["payload"]["secretValue"] == secret
    assert result["exitCode"] == 0
    assert secret not in json.dumps(result)
    assert "stdout" not in result and "stderr" not in result


def test_real_ssh_host_key_mismatch_stops_before_authentication(monkeypatch):
    transport, host, thread, received, errors = _run_server(
        monkeypatch,
        wrong_host_key=_new_ed25519_key(),
    )
    # The stored key is deliberately replaced with a different, valid Ed25519 pin.
    wrong_pin = _new_ed25519_key()
    monkeypatch.setattr(
        ssh_module,
        "load_confirmed_ssh_host_key",
        lambda value: ("ssh-ed25519", base64.b64encode(wrong_pin.asbytes()).decode("ascii"), station_ssh_trust._fingerprint(wrong_pin)),
    )

    with pytest.raises(StationTrustMismatch):
        transport.execute(host, "status-json", [])
    thread.join(timeout=6)
    assert not received
    assert not thread.is_alive()


def test_real_ssh_public_key_authentication_failure_is_not_reported_as_success(monkeypatch):
    wrong_client_key = _new_ed25519_key()
    transport, host, thread, received, errors = _run_server(monkeypatch, expected_client_key=wrong_client_key)

    with pytest.raises(StationAuthenticationFailed):
        transport.execute(host, "identity", [])
    thread.join(timeout=6)
    assert not received
    assert not thread.is_alive()


def test_invalid_operation_is_rejected_before_a_network_connection(monkeypatch):
    transport = SshTransport()
    monkeypatch.setattr(transport, "_dispatch", lambda *args: pytest.fail("network dispatch ran before allowlist"))

    with pytest.raises(StationCommandRejected):
        transport.execute({"address": "127.0.0.1"}, "shell", ["-c", "id"])


def test_invalid_dispatcher_json_is_reported_as_unreachable(monkeypatch):
    transport, host, thread, received, errors = _run_server(monkeypatch, handler=lambda envelope: "not a result")

    with pytest.raises(StationUnreachable, match="invalid result"):
        transport.execute(host, "identity", [])
    _finish(thread, errors)
    assert received[0]["command"] == "station"


def test_invalid_or_unpinned_endpoint_is_rejected_before_auth(monkeypatch):
    transport = SshTransport()
    monkeypatch.setattr(ssh_module, "load_ssh_credential", lambda _ref: None)

    with pytest.raises(StationUnreachable, match="endpoint"):
        transport._open({"address": "", "management": {"transport": "ssh"}})
    with pytest.raises(StationAuthenticationFailed):
        transport._open({"address": "127.0.0.1", "management": {"transport": "ssh", "port": 22}})
