"""Select a single station transport at the management boundary."""

import os
from datetime import datetime, timedelta
import json
import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional

from errors import is_winrm_unreachable_error
from station_errors import StationCommandRejected, StationError, StationShutdownBlocked, StationUnreachable
from station_operation_reconciliation import execute_with_operation_reconciliation
from station_transport import normalize_command_result, validate_station_command
from station_shutdown_policy import shutdown_preflight_error
from transports.ssh import SshTransport


class StationTransportRuntime:
    def __init__(
        self,
        *,
        run_winrm_command: Callable[..., Dict[str, Any]],
        read_winrm_file: Callable[..., str],
        write_winrm_file: Callable[..., Any],
        remove_winrm_file: Callable[..., Any],
        run_winrm_powershell: Optional[Callable[..., Any]] = None,
        ssh_transport: Optional[SshTransport] = None,
    ):
        self._run_winrm_command = run_winrm_command
        self._read_winrm_file = read_winrm_file
        self._write_winrm_file = write_winrm_file
        self._remove_winrm_file = remove_winrm_file
        self._run_winrm_powershell = run_winrm_powershell
        self._ssh = ssh_transport or SshTransport(
            connect_timeout=float(os.getenv("OPS_SSH_CONNECT_TIMEOUT", "5")),
            command_timeout=float(os.getenv("OPS_SSH_COMMAND_TIMEOUT", "30")),
            max_parallel_per_host=int(os.getenv("OPS_SSH_MAX_PARALLEL_PER_HOST", "2")),
        )

    @staticmethod
    def transport_for(host: Mapping[str, Any]) -> str:
        management = host.get("management")
        if isinstance(management, Mapping) and management.get("transport"):
            return str(management["transport"]).lower()
        return str(host.get("management_transport") or "winrm").lower()

    def execute(
        self,
        host: Mapping[str, Any],
        command: str,
        args: List[str],
        *legacy_args: Any,
        request_id: Optional[str] = None,
        dispatcher_request: Optional[Mapping[str, Any]] = None,
        **legacy_kwargs: Any,
    ) -> Dict[str, Any]:
        args = list(args or [])
        transport = self.transport_for(host)
        if command == "power" and args and args[0] == "shutdown":
            status_result = self.execute(host, "status-json", [])
            if int(status_result.get("exitCode", 2)) >= 2:
                raise StationShutdownBlocked(
                    "Station status is unavailable; shutdown was not sent", transport
                )
            try:
                status_payload = json.loads(str(status_result.get("stdout") or ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise StationShutdownBlocked(
                    "Station status is invalid; shutdown was not sent", transport
                ) from exc
            preflight_error = shutdown_preflight_error(status_payload)
            if preflight_error:
                raise StationShutdownBlocked(preflight_error, transport)
            args = [arg for arg in args if not arg.lower().startswith("--require-idle")]
            args = [
                arg for arg in args
                if not arg.lower().startswith("--skip-wake-check")
                and not arg.lower().startswith("--repair-wake")
                and arg.lower() != "--no-repair-wake"
            ]
            args.append("--require-idle")
            if transport == "winrm":
                args.append("--repair-wake=no")
            validate_station_command(command, args)

        if transport == "ssh":
            try:
                if dispatcher_request is None:
                    return self._ssh.execute(host, command, list(args or []), request_id=request_id)
                return self._ssh.execute(host, command, list(args or []), request_id=request_id, dispatcher_request=dispatcher_request)
            except StationError:
                raise
            except Exception as exc:
                raise StationUnreachable() from exc
        if transport != "winrm":
            raise StationUnreachable("Station management transport is unsupported")
        if dispatcher_request is not None:
            envelope = self._build_dispatcher_envelope(command, args, request_id, dispatcher_request)
            self._require_winrm_lease_dispatcher(host)
            wire_argument = "--request-json=" + json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)
            if len(wire_argument) > 16000:
                raise StationCommandRejected()
            operation_id = str(envelope["id"])
            return execute_with_operation_reconciliation(
                read_status=lambda: self._winrm_operation_status(
                    host, operation_id, command, *legacy_args, **legacy_kwargs
                ),
                dispatch=lambda: self._normalize_winrm_dispatch_result(
                    command,
                    args,
                    envelope,
                    self._run_winrm_command(
                        host, "lease-dispatch", [wire_argument], *legacy_args, **legacy_kwargs
                    ),
                ),
                normalize_stored=lambda stored: self._normalize_winrm_stored_result(
                    command, args, operation_id, stored
                ),
                classify_uncertain=self._winrm_uncertain_failure,
            )
        result = self._run_winrm_command(host, command, args, *legacy_args, **legacy_kwargs)
        exit_code = int(result.get("exit_code", result.get("exitCode", 2)))
        normalized = normalize_command_result(
            command,
            exit_code,
            str(result.get("stdout") or ""),
            str(result.get("stderr") or ""),
            int(result.get("duration_ms", result.get("durationMs", 0)) or 0),
            "winrm",
            request_id=request_id,
            metadata={"platform": "windows"},
        )
        # Keep the historical snake_case fields while lifecycle consumers migrate.
        normalized.update({"exit_code": normalized["exitCode"], "duration_ms": normalized["durationMs"]})
        return normalized

    def _require_winrm_lease_dispatcher(self, host: Mapping[str, Any]) -> None:
        try:
            status_result = self._run_winrm_command(host, "status-json", [])
        except StationUnreachable as exc:
            raise StationUnreachable(str(exc), "winrm") from exc
        except StationError:
            raise
        except Exception as exc:
            if is_winrm_unreachable_error(exc):
                raise StationUnreachable("Station status is unavailable for lease capability negotiation", "winrm") from exc
            raise
        if not isinstance(status_result, Mapping):
            raise StationUnreachable("Station status is invalid for lease capability negotiation", "winrm")
        if int(status_result.get("exit_code", status_result.get("exitCode", 2))) >= 2:
            raise StationUnreachable("Station status is unavailable for lease capability negotiation", "winrm")
        try:
            status = json.loads(str(status_result.get("stdout") or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station status is invalid for lease capability negotiation", "winrm") from exc
        capabilities = status.get("managementCapabilities") if isinstance(status, dict) else None
        if (
            not isinstance(capabilities, list)
            or "reservation-lease-v1" not in capabilities
            or "operation-status-v1" not in capabilities
        ):
            raise StationUnreachable("Station does not advertise durable lease and operation-status support", "winrm")

    @staticmethod
    def _winrm_uncertain_failure(error: Exception) -> Optional[StationUnreachable]:
        if isinstance(error, StationUnreachable):
            return StationUnreachable(str(error), "winrm")
        if is_winrm_unreachable_error(error):
            return StationUnreachable("WinRM command outcome is uncertain", "winrm")
        return None

    def _winrm_operation_status(
        self,
        host: Mapping[str, Any],
        operation_id: str,
        command: str,
        *legacy_args: Any,
        **legacy_kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        envelope = {
            "schemaVersion": 2,
            "id": str(uuid.uuid4()),
            "operation": "operation.status",
            "operationId": operation_id,
        }
        wire_argument = "--request-json=" + json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)
        try:
            raw = self._run_winrm_command(
                host, "lease-dispatch", [wire_argument], *legacy_args, **legacy_kwargs
            )
            result = self._normalize_winrm_dispatch_result(
                "operation.status", [], envelope, raw
            )
        except StationUnreachable as exc:
            raise StationUnreachable(str(exc), "winrm") from exc
        except StationError:
            raise
        except Exception as exc:
            if not is_winrm_unreachable_error(exc):
                raise
            raise StationUnreachable("Station operation status could not be read", "winrm") from exc
        if result["exitCode"] >= 2:
            raise StationUnreachable("Station operation status could not be read", "winrm")
        try:
            record = json.loads(str(result.get("stdout") or ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station operation status is malformed", "winrm") from exc
        if not isinstance(record, dict):
            raise StationUnreachable("Station operation status is malformed", "winrm")
        state = record.get("state")
        reported_operation_id = record.get("operationId")
        if reported_operation_id is not None and reported_operation_id != operation_id:
            raise StationUnreachable("Station operation status is malformed", "winrm")
        if state == "not-found":
            if reported_operation_id != operation_id:
                raise StationUnreachable("Station operation status is malformed", "winrm")
            return None
        if state == "processing":
            raise StationUnreachable("Station operation is still in progress", "winrm")
        stored = record.get("result")
        if state not in {"completed", "recovery-required"} or not isinstance(stored, dict):
            raise StationUnreachable("Station operation status is incomplete", "winrm")
        self._validate_winrm_stored_result(stored, operation_id, command)
        return stored

    @staticmethod
    def _validate_winrm_stored_result(
        result: Mapping[str, Any], operation_id: str, command: str
    ) -> None:
        try:
            completed = datetime.fromisoformat(str(result.get("completedAt", "")).replace("Z", "+00:00"))
        except ValueError as exc:
            raise StationUnreachable("Station returned an invalid stored result", "winrm") from exc
        exit_code = result.get("exitCode")
        expected_outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
        if (
            result.get("id") != operation_id
            or result.get("command") != command
            or type(exit_code) is not int
            or exit_code < 0
            or completed.tzinfo is None
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
            raise StationUnreachable("Station returned an invalid stored result", "winrm")

    @staticmethod
    def _normalize_winrm_stored_result(
        command: str, args: List[str], operation_id: str, result: Mapping[str, Any]
    ) -> Dict[str, Any]:
        exit_code = int(result["exitCode"])
        normalized = normalize_command_result(
            command,
            exit_code,
            str(result.get("stdout") or ""),
            str(result.get("stderr") or ""),
            int(result.get("durationMs", 0) or 0),
            "winrm",
            request_id=operation_id,
            metadata=dict(result.get("metadata") or {}),
            options={"args": list(args)},
        )
        normalized["completedAt"] = str(result["completedAt"])
        normalized["message"] = str(result["message"])
        normalized.update({"exit_code": normalized["exitCode"], "duration_ms": normalized["durationMs"]})
        return normalized

    @staticmethod
    def _build_dispatcher_envelope(
        command: str,
        args: List[str],
        request_id: Optional[str],
        dispatcher_request: Mapping[str, Any],
    ) -> Dict[str, Any]:
        validate_station_command(command, args)
        if command not in {"prepare-session", "release-session"} or not isinstance(dispatcher_request, Mapping):
            raise StationCommandRejected()
        operation_id = str(dispatcher_request.get("requestId") or request_id or "")
        if (
            not operation_id
            or len(operation_id) > 96
            or re.fullmatch(r"[A-Za-z0-9_.:-]+", operation_id) is None
            or (request_id is not None and request_id != operation_id)
        ):
            raise StationCommandRejected()
        issued_at = dispatcher_request.get("issuedAt")
        execute_before = dispatcher_request.get("executeBefore")
        context = dispatcher_request.get("context")
        timeout_seconds = dispatcher_request.get("timeoutSeconds", 180 if command == "prepare-session" else 90)
        if (
            not isinstance(issued_at, str)
            or not issued_at.endswith("Z")
            or not isinstance(execute_before, str)
            or not execute_before.endswith("Z")
            or not isinstance(context, Mapping)
        ):
            raise StationCommandRejected()
        try:
            issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            deadline = datetime.fromisoformat(execute_before.replace("Z", "+00:00"))
            timeout_seconds = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise StationCommandRejected() from exc
        if (
            issued.tzinfo is None
            or deadline.tzinfo is None
            or issued.utcoffset() != timedelta(0)
            or deadline.utcoffset() != timedelta(0)
            or deadline <= issued
            or deadline - issued > timedelta(minutes=5)
            or not 1 <= timeout_seconds <= 300
        ):
            raise StationCommandRejected()
        return {
            "schemaVersion": 2,
            "id": operation_id,
            "operation": "execute",
            "command": command,
            "args": list(args),
            "issuedAt": issued_at,
            "executeBefore": execute_before,
            "context": dict(context),
        }

    @staticmethod
    def _normalize_winrm_dispatch_result(
        command: str,
        args: List[str],
        envelope: Mapping[str, Any],
        raw: Mapping[str, Any],
    ) -> Dict[str, Any]:
        try:
            response = json.loads(str(raw.get("stdout") or ""))
            completed = datetime.fromisoformat(str(response.get("completedAt", "")).replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StationUnreachable("Station dispatcher returned an invalid result") from exc
        exit_code = response.get("exitCode") if isinstance(response, dict) else None
        if (
            not isinstance(response, dict)
            or response.get("id") != envelope.get("id")
            or response.get("command") != command
            or type(exit_code) is not int
            or exit_code < 0
            or completed.tzinfo is None
            or completed.utcoffset() != timedelta(0)
            or type(raw.get("exit_code", raw.get("exitCode", exit_code))) is not int
            or raw.get("exit_code", raw.get("exitCode", exit_code)) != exit_code
            or not isinstance(response.get("message"), str)
            or not isinstance(response.get("stdout"), str)
            or not isinstance(response.get("stderr"), str)
            or type(response.get("durationMs")) is not int
            or response["durationMs"] < 0
            or not isinstance(response.get("metadata"), dict)
        ):
            raise StationUnreachable("Station dispatcher returned an invalid result")
        expected_outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
        if (
            type(response.get("success")) is not bool
            or response["success"] != (exit_code < 2)
            or response.get("outcome") != expected_outcome
        ):
            raise StationUnreachable("Station dispatcher returned an inconsistent result")
        if exit_code < 2 and envelope.get("operation") == "execute":
            lease = response["metadata"].get("lease")
            expected_generation = envelope["context"].get("generation")
            if envelope["command"] == "prepare-session":
                expected_generation = None
            if (
                not isinstance(lease, Mapping)
                or lease.get("leaseId") != envelope["context"].get("leaseId")
                or type(lease.get("generation")) is not int
                or lease["generation"] < 1
                or (expected_generation is not None and lease["generation"] != expected_generation)
                or lease.get("expiresAt") != envelope["context"].get("expiresAt")
                or lease.get("state") not in (
                    {"active", "recovery-required"}
                    if envelope["command"] == "prepare-session"
                    else {"released", "recovery-required"}
                )
            ):
                raise StationUnreachable("Station dispatcher returned an invalid lease result")
        normalized = normalize_command_result(
            command,
            exit_code,
            response["stdout"],
            response["stderr"],
            response["durationMs"],
            "winrm",
            request_id=str(response["id"]),
            metadata=dict(response["metadata"]),
            options={"args": list(args)},
        )
        normalized["completedAt"] = response["completedAt"]
        normalized["message"] = response["message"]
        normalized.update({"exit_code": normalized["exitCode"], "duration_ms": normalized["durationMs"]})
        return normalized

    def read_artifact(self, host: Mapping[str, Any], artifact_id: str) -> str:
        transport = self.transport_for(host)
        if transport == "ssh":
            try:
                return self._ssh.read_artifact(host, artifact_id)
            except StationError:
                raise
            except Exception as exc:
                raise StationUnreachable() from exc
        path_key = {"heartbeat": "heartbeat_path", "session-events": "events_path"}.get(artifact_id)
        if not path_key:
            raise ValueError("station artifact is not allowlisted")
        path = host.get(path_key)
        if not path:
            raise ValueError("station artifact path is not configured")
        return self._read_winrm_file(host, path, None, None, None, None, None)

    def read_remote_file(self, host: Mapping[str, Any], path: str, *args: Any) -> str:
        if self.transport_for(host) == "ssh":
            if path in {"heartbeat", "status", "session-events"}:
                return self.read_artifact(host, path)
            for artifact_id, key in (("heartbeat", "heartbeat_path"), ("session-events", "events_path")):
                if str(host.get(key) or "") == str(path):
                    return self.read_artifact(host, artifact_id)
            raise ValueError("SSH station paths are logical artifacts, not arbitrary remote files")
        return self._read_winrm_file(host, path, *args)

    def write_remote_file(self, host: Mapping[str, Any], *args: Any) -> Any:
        if self.transport_for(host) == "ssh":
            raise ValueError("SSH station file writes are not part of the transport contract")
        return self._write_winrm_file(host, *args)

    def remove_remote_file(self, host: Mapping[str, Any], *args: Any) -> Any:
        if self.transport_for(host) == "ssh":
            raise ValueError("SSH station file deletes are not part of the transport contract")
        return self._remove_winrm_file(host, *args)

    def probe(self, host: Mapping[str, Any]) -> Dict[str, Any]:
        if self.transport_for(host) == "ssh":
            return self._ssh.probe(host)
        result = self.execute(host, "status-json", [])
        return {"reachable": int(result.get("exitCode", 2)) < 2, "transport": "winrm"}

    def write_secret(self, host: Mapping[str, Any], secret_id: str, value: str) -> Dict[str, Any]:
        if secret_id != "fmu-internal-token" or not value or len(value) > 4096:
            raise ValueError("station secret operation is invalid")
        if self.transport_for(host) == "ssh":
            return self._ssh.write_secret(host, secret_id, value)
        if self.transport_for(host) == "winrm" and self._run_winrm_powershell:
            from fmu_station_enrollment import build_fmu_station_provision_script
            self._run_winrm_powershell(
                host=host, script=build_fmu_station_provision_script(value),
                user=None, password=None, transport=None, use_ssl=None, port=None,
            )
            return {"exitCode": 0, "outcome": "success", "transport": "winrm", "secretId": secret_id}
        raise ValueError("secure station secret operation is not configured")

    def clear_secret(self, host: Mapping[str, Any], secret_id: str) -> Dict[str, Any]:
        if secret_id != "fmu-internal-token":
            raise ValueError("station secret operation is invalid")
        if self.transport_for(host) == "ssh":
            return self._ssh.clear_secret(host, secret_id)
        if self.transport_for(host) == "winrm" and self._run_winrm_powershell:
            from fmu_station_enrollment import build_fmu_station_release_script
            self._run_winrm_powershell(
                host=host, script=build_fmu_station_release_script(),
                user=None, password=None, transport=None, use_ssl=None, port=None,
            )
            return {"exitCode": 0, "outcome": "success", "transport": "winrm", "secretId": secret_id}
        raise ValueError("secure station secret operation is not configured")


def create_station_transport_runtime(**kwargs: Any) -> StationTransportRuntime:
    return StationTransportRuntime(**kwargs)


__all__ = ["StationTransportRuntime", "create_station_transport_runtime"]
