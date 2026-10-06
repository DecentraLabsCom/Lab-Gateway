"""Paramiko transport using pinned host keys and a fixed structured dispatcher."""

import base64
import io
import json
import socket
import threading
import time
from typing import Any, Dict, List, Mapping, Optional

import paramiko

from station_credentials import load_ssh_credential
from station_errors import StationAuthenticationFailed, StationTrustMismatch, StationUnreachable
from station_ssh_trust import load_confirmed_ssh_host_key
from station_transport import normalize_command_result, validate_station_command


_LOCKS_GUARD = threading.Lock()
_HOST_LOCKS: Dict[str, threading.BoundedSemaphore] = {}
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def _management(host: Mapping[str, Any]) -> Mapping[str, Any]:
    value = host.get("management")
    return value if isinstance(value, Mapping) else {}


def _host_lock(host: Mapping[str, Any], limit: int) -> threading.BoundedSemaphore:
    key = str(host.get("name") or host.get("address") or "").lower()
    with _LOCKS_GUARD:
        if key not in _HOST_LOCKS:
            _HOST_LOCKS[key] = threading.BoundedSemaphore(max(1, min(int(limit), 8)))
        return _HOST_LOCKS[key]


class SshTransport:
    name = "ssh"

    def __init__(self, *, connect_timeout: float = 5.0, command_timeout: float = 30.0, max_parallel_per_host: int = 2):
        self.connect_timeout = max(1.0, min(connect_timeout, 30.0))
        self.command_timeout = max(1.0, min(command_timeout, 300.0))
        self.max_parallel_per_host = max(1, min(max_parallel_per_host, 8))

    def _open(self, host: Mapping[str, Any]) -> paramiko.Transport:
        management = _management(host)
        address = str(host.get("address") or "").strip()
        try:
            port = int(management.get("port") or host.get("management_port") or 22)
        except (TypeError, ValueError) as exc:
            raise StationUnreachable("SSH port is invalid") from exc
        if not address or not 1 <= port <= 65535:
            raise StationUnreachable("SSH endpoint is invalid")
        ref = str(management.get("credentialRef") or host.get("credential_ref") or address)
        credential = load_ssh_credential(ref)
        if not credential:
            raise StationAuthenticationFailed("SSH service credential is missing or unavailable")
        key_type, key_data, _fingerprint = load_confirmed_ssh_host_key(host)
        expected = paramiko.PKey.from_type_string(key_type, base64.b64decode(key_data, validate=True))
        sock = None
        transport = None
        try:
            sock = socket.create_connection((address, port), timeout=self.connect_timeout)
            transport = paramiko.Transport(sock)
            transport.start_client(timeout=self.connect_timeout)
            actual = transport.get_remote_server_key()
            if actual.get_name() != expected.get_name() or actual.asbytes() != expected.asbytes():
                raise StationTrustMismatch()
            private_key = paramiko.Ed25519Key.from_private_key(io.StringIO(credential["privateKey"]))
            transport.auth_publickey(credential["username"], private_key)
            if not transport.is_authenticated():
                raise StationAuthenticationFailed()
            return transport
        except (StationTrustMismatch, StationAuthenticationFailed):
            if transport:
                transport.close()
            elif sock:
                sock.close()
            raise
        except paramiko.AuthenticationException as exc:
            if transport:
                transport.close()
            elif sock:
                sock.close()
            raise StationAuthenticationFailed() from exc
        except (OSError, socket.timeout, paramiko.SSHException, ValueError) as exc:
            if transport:
                transport.close()
            elif sock:
                sock.close()
            raise StationUnreachable() from exc

    def _dispatch(self, host: Mapping[str, Any], envelope: Dict[str, Any]) -> Dict[str, Any]:
        lock = _host_lock(host, self.max_parallel_per_host)
        acquired = lock.acquire(timeout=self.connect_timeout)
        if not acquired:
            raise StationUnreachable("Station command concurrency limit reached")
        started = time.monotonic()
        transport = None
        channel = None
        try:
            transport = self._open(host)
            channel = transport.open_session(timeout=self.connect_timeout)
            channel.settimeout(self.command_timeout)
            channel.exec_command("station")  # Authorized key ForceCommand ignores this fixed token.
            request = (json.dumps(envelope, separators=(",", ":")) + "\n").encode("utf-8")
            channel.sendall(request)
            channel.shutdown_write()
            stdout = bytearray()
            stderr = bytearray()
            deadline = time.monotonic() + self.command_timeout
            while not channel.exit_status_ready():
                if time.monotonic() > deadline:
                    raise StationUnreachable("SSH command timed out")
                if channel.recv_ready():
                    stdout.extend(channel.recv(32768))
                if channel.recv_stderr_ready():
                    stderr.extend(channel.recv_stderr(32768))
                if len(stdout) + len(stderr) > _MAX_OUTPUT_BYTES:
                    raise StationUnreachable("Station command output exceeded the limit")
                time.sleep(0.01)
            while channel.recv_ready():
                stdout.extend(channel.recv(32768))
            while channel.recv_stderr_ready():
                stderr.extend(channel.recv_stderr(32768))
            if len(stdout) + len(stderr) > _MAX_OUTPUT_BYTES:
                raise StationUnreachable("Station command output exceeded the limit")
            response = json.loads(stdout.decode("utf-8"))
            if not isinstance(response, dict) or not isinstance(response.get("exitCode"), int):
                raise StationUnreachable("Station dispatcher returned an invalid result")
            response.setdefault("transport", "ssh")
            response.setdefault("durationMs", int((time.monotonic() - started) * 1000))
            response.setdefault("stderr", stderr.decode("utf-8", errors="replace"))
            return response
        except (socket.timeout, TimeoutError) as exc:
            raise StationUnreachable("SSH command timed out") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station dispatcher returned an invalid response") from exc
        finally:
            if channel:
                channel.close()
            if transport:
                transport.close()
            lock.release()

    def execute(self, host: Mapping[str, Any], command: str, args: List[str], *, request_id: Optional[str] = None) -> Dict[str, Any]:
        validate_station_command(command, args)
        envelope = {"schemaVersion": 1, "id": request_id, "operation": "execute", "command": command, "args": args}
        result = self._dispatch(host, envelope)
        exit_code = int(result.get("exitCode", 2))
        normalized = normalize_command_result(
            command,
            exit_code,
            str(result.get("stdout") or ""),
            str(result.get("stderr") or ""),
            int(result.get("durationMs", 0) or 0),
            "ssh",
            request_id=str(result.get("id") or request_id or "") or None,
            metadata=dict(result.get("metadata") or {}),
            options={"args": list(args)},
        )
        if result.get("completedAt"):
            normalized["completedAt"] = str(result["completedAt"])
        if result.get("message"):
            normalized["message"] = str(result["message"])
        return normalized

    def read_artifact(self, host: Mapping[str, Any], artifact_id: str) -> str:
        validate_station_command("artifact.read", [artifact_id])
        result = self._dispatch(host, {"schemaVersion": 1, "operation": "artifact.read", "artifact": artifact_id})
        if int(result.get("exitCode", 2)) >= 2:
            raise StationUnreachable("Station artifact could not be read")
        return str(result.get("stdout") or "")

    def probe(self, host: Mapping[str, Any]) -> Dict[str, Any]:
        result = self.execute(host, "identity", [])
        if int(result.get("exitCode", 2)) >= 2:
            raise StationUnreachable("SSH endpoint is not a Lab Station dispatcher")
        try:
            identity = json.loads(str(result.get("stdout") or "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station identity response is invalid") from exc
        if not isinstance(identity, dict) or identity.get("contractVersion") != "3.0.0":
            raise StationUnreachable("SSH endpoint does not implement Station Contract v3")
        return {"reachable": True, "transport": "ssh", "identity": identity}

    def write_secret(self, host: Mapping[str, Any], secret_id: str, value: str) -> Dict[str, Any]:
        """Send a named secret over the authenticated SSH channel, never argv/stdout."""
        if secret_id != "fmu-internal-token" or not value or len(value) > 4096:
            raise ValueError("station secret operation is invalid")
        result = self._dispatch(host, {
            "schemaVersion": 1,
            "operation": "secret.set",
            "secretId": secret_id,
            "secretValue": value,
        })
        result.pop("stdout", None)
        result.pop("stderr", None)
        if int(result.get("exitCode", 2)) >= 2:
            raise StationUnreachable("Station secret provisioning failed")
        return result

    def clear_secret(self, host: Mapping[str, Any], secret_id: str) -> Dict[str, Any]:
        if secret_id != "fmu-internal-token":
            raise ValueError("station secret operation is invalid")
        result = self._dispatch(host, {
            "schemaVersion": 1,
            "operation": "secret.clear",
            "secretId": secret_id,
        })
        result.pop("stdout", None)
        result.pop("stderr", None)
        if int(result.get("exitCode", 2)) >= 2:
            raise StationUnreachable("Station secret release failed")
        return result


__all__ = ["SshTransport"]
