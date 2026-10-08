"""Select a single station transport at the management boundary."""

import os
from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional

from station_errors import StationError, StationUnreachable
from station_transport import normalize_command_result
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
        transport = self.transport_for(host)
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
            raise StationUnreachable("Lease dispatcher requests require SSH transport")
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
