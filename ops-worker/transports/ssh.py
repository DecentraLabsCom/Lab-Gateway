"""Paramiko transport using pinned host keys and a fixed structured dispatcher."""

import base64
from datetime import datetime, timedelta
import io
import json
import socket
import threading
import time
import uuid
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

    def _dispatch(
        self,
        host: Mapping[str, Any],
        envelope: Dict[str, Any],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        budget = self.command_timeout if timeout_seconds is None else max(1.0, min(float(timeout_seconds), 300.0))
        lock = _host_lock(host, self.max_parallel_per_host)
        acquired = lock.acquire(timeout=self.connect_timeout)
        if not acquired:
            raise StationUnreachable("Station command concurrency limit reached")
        transport = None
        channel = None
        try:
            transport = self._open(host)
            channel = transport.open_session(timeout=self.connect_timeout)
            channel.settimeout(budget)
            channel.exec_command("station")  # Authorized key ForceCommand ignores this fixed token.
            request = (json.dumps(envelope, separators=(",", ":")) + "\n").encode("utf-8")
            channel.sendall(request)
            channel.shutdown_write()
            stdout = bytearray()
            stderr = bytearray()
            deadline = time.monotonic() + budget
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
            operation = envelope.get("operation")
            expected_command = envelope.get("command") if operation == "execute" else operation
            exit_code = response.get("exitCode") if isinstance(response, dict) else None
            if (
                not isinstance(response, dict)
                or response.get("id") != envelope.get("id")
                or response.get("command") != expected_command
                or type(exit_code) is not int
                or exit_code < 0
            ):
                raise StationUnreachable("Station dispatcher returned an invalid result")
            try:
                completed_at = datetime.fromisoformat(str(response.get("completedAt", "")).replace("Z", "+00:00"))
            except ValueError as exc:
                raise StationUnreachable("Station dispatcher returned an invalid result") from exc
            if (
                completed_at.tzinfo is None
                or not isinstance(response.get("message"), str)
                or not isinstance(response.get("stdout"), str)
                or not isinstance(response.get("stderr"), str)
                or type(response.get("durationMs")) is not int
                or response["durationMs"] < 0
                or not isinstance(response.get("metadata"), dict)
            ):
                raise StationUnreachable("Station dispatcher returned an incomplete result")
            expected_outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
            if (
                type(response.get("success")) is not bool
                or response["success"] != (exit_code < 2)
                or response.get("outcome") != expected_outcome
            ):
                raise StationUnreachable("Station dispatcher returned an inconsistent result")
            response.setdefault("transport", "ssh")
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

    def _require_dispatcher_v2(self, host: Mapping[str, Any]) -> None:
        identity = self._dispatch(host, {
            "schemaVersion": 1,
            "id": str(uuid.uuid4()),
            "operation": "execute",
            "command": "identity",
            "args": [],
        }, timeout_seconds=15)
        try:
            payload = json.loads(str(identity.get("stdout") or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station identity does not advertise dispatcher capabilities") from exc
        versions = payload.get("dispatcherVersions") if isinstance(payload, dict) else None
        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        if (
            not isinstance(versions, list)
            or 2 not in versions
            or not isinstance(capabilities, list)
            or "reservation-lease-v1" not in capabilities
        ):
            raise StationUnreachable("Station does not support reservation lease dispatcher v2")

    def _operation_status(
        self,
        host: Mapping[str, Any],
        operation_id: str,
        command: str,
    ) -> Optional[Dict[str, Any]]:
        result = self._dispatch(host, {
            "schemaVersion": 2,
            "id": str(uuid.uuid4()),
            "operation": "operation.status",
            "operationId": operation_id,
        }, timeout_seconds=15)
        if result["exitCode"] >= 2:
            raise StationUnreachable("Station operation status could not be read")
        try:
            record = json.loads(str(result.get("stdout") or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station operation status is malformed") from exc
        if not isinstance(record, dict):
            raise StationUnreachable("Station operation status is malformed")
        state = record.get("state")
        if state == "not-found":
            return None
        if state == "processing":
            raise StationUnreachable("Station operation is still in progress")
        if state not in {"completed", "recovery-required"} or not isinstance(record.get("result"), dict):
            raise StationUnreachable("Station operation status is incomplete")
        stored = record["result"]
        self._validate_correlated_result(stored, operation_id, command)
        return stored

    @staticmethod
    def _validate_correlated_result(result: Mapping[str, Any], request_id: str, command: str) -> None:
        exit_code = result.get("exitCode")
        try:
            completed_at = datetime.fromisoformat(str(result.get("completedAt", "")).replace("Z", "+00:00"))
        except ValueError as exc:
            raise StationUnreachable("Station returned an invalid stored result") from exc
        expected_outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
        if (
            result.get("id") != request_id
            or result.get("command") != command
            or type(exit_code) is not int
            or exit_code < 0
            or completed_at.tzinfo is None
            or not isinstance(result.get("message"), str)
            or not isinstance(result.get("stdout"), str)
            or not isinstance(result.get("stderr"), str)
            or type(result.get("durationMs")) is not int
            or result["durationMs"] < 0
            or not isinstance(result.get("metadata"), dict)
            or type(result.get("success")) is not bool
            or result["success"] != (exit_code < 2)
            or result.get("outcome") != expected_outcome
        ):
            raise StationUnreachable("Station returned an invalid stored result")

    def execute(
        self,
        host: Mapping[str, Any],
        command: str,
        args: List[str],
        *,
        request_id: Optional[str] = None,
        dispatcher_request: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        validate_station_command(command, args)
        if dispatcher_request is None:
            request_id = request_id or str(uuid.uuid4())
            envelope = {"schemaVersion": 1, "id": request_id, "operation": "execute", "command": command, "args": args}
            result = self._dispatch(host, envelope)
        else:
            if command not in {"prepare-session", "release-session"}:
                raise StationCommandRejected()
            operation_id = str(dispatcher_request.get("requestId") or request_id or "")
            if not operation_id or len(operation_id) > 96 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for char in operation_id):
                raise StationCommandRejected()
            if request_id and request_id != operation_id:
                raise StationCommandRejected()
            issued_at = dispatcher_request.get("issuedAt")
            execute_before = dispatcher_request.get("executeBefore")
            context = dispatcher_request.get("context")
            timeout_seconds = dispatcher_request.get("timeoutSeconds", 180 if command == "prepare-session" else 90)
            if not isinstance(issued_at, str) or not isinstance(execute_before, str) or not isinstance(context, Mapping):
                raise StationCommandRejected()
            try:
                issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
                deadline = datetime.fromisoformat(execute_before.replace("Z", "+00:00"))
                timeout_seconds = float(timeout_seconds)
            except (ValueError, TypeError) as exc:
                raise StationCommandRejected() from exc
            if (
                issued.tzinfo is None
                or deadline.tzinfo is None
                or issued.utcoffset().total_seconds() != 0
                or deadline.utcoffset().total_seconds() != 0
                or deadline <= issued
                or deadline - issued > timedelta(minutes=5)
                or not 1 <= timeout_seconds <= 300
            ):
                raise StationCommandRejected()
            self._require_dispatcher_v2(host)
            previous = self._operation_status(host, operation_id, command)
            if previous is not None:
                result = previous
            else:
                envelope = {
                    "schemaVersion": 2,
                    "id": operation_id,
                    "operation": "execute",
                    "command": command,
                    "args": args,
                    "issuedAt": issued_at,
                    "executeBefore": execute_before,
                    "context": dict(context),
                }
                try:
                    result = self._dispatch(host, envelope, timeout_seconds=timeout_seconds)
                except StationUnreachable as original_error:
                    try:
                        previous = self._operation_status(host, operation_id, command)
                    except StationUnreachable:
                        raise original_error
                    if previous is None:
                        raise original_error
                    result = previous
            request_id = operation_id
        exit_code = result["exitCode"]
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
        result = self._dispatch(host, {"schemaVersion": 1, "id": str(uuid.uuid4()), "operation": "artifact.read", "artifact": artifact_id})
        if result["exitCode"] >= 2:
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
            "id": str(uuid.uuid4()),
            "operation": "secret.set",
            "secretId": secret_id,
            "secretValue": value,
        })
        result.pop("stdout", None)
        result.pop("stderr", None)
        if result["exitCode"] >= 2:
            raise StationUnreachable("Station secret provisioning failed")
        return result

    def clear_secret(self, host: Mapping[str, Any], secret_id: str) -> Dict[str, Any]:
        if secret_id != "fmu-internal-token":
            raise ValueError("station secret operation is invalid")
        result = self._dispatch(host, {
            "schemaVersion": 1,
            "id": str(uuid.uuid4()),
            "operation": "secret.clear",
            "secretId": secret_id,
        })
        result.pop("stdout", None)
        result.pop("stderr", None)
        if result["exitCode"] >= 2:
            raise StationUnreachable("Station secret release failed")
        return result


__all__ = ["SshTransport"]
