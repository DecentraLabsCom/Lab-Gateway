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


def _run_server(monkeypatch, *, handler=None, expected_client_key=None, wrong_host_key=None):
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
    listener.listen(1)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    received = []
    errors = []
    auth = _GatewayClient("labstation-ops", expected_client_key)

    def serve():
        connection = None
        transport = None
        channel = None
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
            received.append({"command": auth.exec_command, "payload": json.loads(request.decode("utf-8"))})
            response = handler(received[-1]["payload"]) if handler else {
                "id": received[-1]["payload"].get("id", "server-id"),
                "command": received[-1]["payload"].get("command", "artifact.read"),
                "exitCode": 0,
                "stdout": "{\"contractVersion\":\"3.0.0\",\"host\":\"linux-1\"}",
                "stderr": "",
                "metadata": {},
            }
            channel.sendall((json.dumps(response) + "\n").encode("utf-8"))
            channel.send_exit_status(0)
        except Exception as exc:  # surfaced in the test thread after the network path is closed
            errors.append(exc)
        finally:
            if channel:
                channel.close()
            if transport:
                transport.close()
            if connection:
                connection.close()
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
            "completedAt": "2026-10-06T12:00:00Z",
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


def test_real_ssh_identity_probe_requires_station_contract_v3(monkeypatch):
    transport, host, thread, received, errors = _run_server(monkeypatch)

    result = transport.probe(host)

    _finish(thread, errors)
    assert result["reachable"] is True
    assert result["transport"] == "ssh"
    assert result["identity"]["contractVersion"] == "3.0.0"
    assert received[0]["payload"]["command"] == "identity"


def test_real_ssh_secret_enrollment_keeps_secret_out_of_the_response(monkeypatch):
    secret = "0123456789abcdef0123456789abcdef"
    transport, host, thread, received, errors = _run_server(
        monkeypatch,
        handler=lambda envelope: {"id": "secret-1", "command": "secret.set", "exitCode": 0, "stdout": "configured", "stderr": "", "metadata": {"secretId": envelope["secretId"]}},
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
