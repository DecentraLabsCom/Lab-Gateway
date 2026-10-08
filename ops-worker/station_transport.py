"""Transport-neutral station command and artifact operations."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol
from uuid import uuid4

from station_errors import StationCommandRejected


@dataclass(frozen=True)
class StationCommandResult:
    id: str
    command: str
    completedAt: str
    success: bool
    exitCode: int
    outcome: str
    message: str
    stdout: str
    stderr: str
    durationMs: int
    transport: str
    metadata: Dict[str, Any]
    options: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StationTransport(Protocol):
    name: str

    def execute(
        self,
        host: Mapping[str, Any],
        command: str,
        args: List[str],
        *,
        request_id: Optional[str] = None,
        dispatcher_request: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]: ...
    def read_artifact(self, host: Mapping[str, Any], artifact_id: str) -> str: ...
    def probe(self, host: Mapping[str, Any]) -> Dict[str, Any]: ...


def normalize_command_result(
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: int,
    transport: str,
    *,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply the common 0/success, 1/warning, 2+/failure contract."""
    if exit_code < 0:
        exit_code = 2
    outcome = "success" if exit_code == 0 else "warning" if exit_code == 1 else "failure"
    return StationCommandResult(
        id=request_id or str(uuid4()),
        command=command,
        completedAt=datetime.now(timezone.utc).isoformat(),
        success=exit_code < 2,
        exitCode=exit_code,
        outcome=outcome,
        message=(stdout.strip().splitlines()[-1].strip() if stdout.strip() else stderr.strip() or outcome),
        stdout=stdout,
        stderr=stderr,
        durationMs=max(0, int(duration_ms)),
        transport=transport,
        metadata=metadata or {},
        options=options or {},
    ).to_dict()


def validate_station_command(command: str, args: List[str]) -> None:
    """Reject every operation outside the structured command allowlist."""
    def safe_option(value: Any, allowed: set[str]) -> bool:
        return (
            isinstance(value, str)
            and len(value) <= 256
            and not any(char in value for char in "\r\n\x00`$|;&><")
            and value.startswith("--")
            and value.split("=", 1)[0] in allowed
        )

    if command == "status-json" or command == "identity":
        allowed = not args
    elif command in {"prepare-session", "release-session", "session guard"}:
        allowed = len(args) <= 12 and all(
            isinstance(value, str)
            and len(value) <= 256
            and not any(char in value for char in "\r\n\x00")
            and value.startswith("--")
            and value.split("=", 1)[0] in {
                "--guard-grace", "--guard-message", "--guard-silent", "--guard-notify",
                "--no-guard", "--user", "--message", "--grace", "--silent",
                "--no-notify", "--reboot", "--reboot-timeout", "--reservation-key",
                "--operation-id",
            }
            for value in args
        )
        if allowed and command == "session guard":
            for value in args:
                key, separator, raw = value.partition("=")
                if key == "--user" and (
                    not separator or not raw or len(raw) > 64 or re.fullmatch(r"[A-Za-z0-9_.-]+", raw) is None
                ):
                    allowed = False
                    break
    elif command == "power":
        allowed = len(args) >= 1 and args[0] in {"shutdown", "hibernate"} and all(
            safe_option(value, {"--delay", "--reason", "--require-wake"}) for value in args[1:]
        )
        if allowed:
            for value in args[1:]:
                key, separator, raw = value.partition("=")
                if key == "--delay" and (not separator or not raw.isdigit() or int(raw) > 3600):
                    allowed = False
                elif key == "--reason" and (not separator or not raw.strip() or len(raw) > 128):
                    allowed = False
                elif key == "--require-wake" and separator and raw not in {"true", "false"}:
                    allowed = False
    elif command == "recovery reboot-if-needed":
        allowed = len(args) <= 4 and all(safe_option(value, {"--force", "--timeout", "--reason"}) for value in args)
        if allowed:
            for value in args:
                key, separator, raw = value.partition("=")
                if key == "--force" and separator:
                    allowed = False
                elif key == "--timeout" and (not separator or not raw.isdigit() or int(raw) > 30):
                    allowed = False
                elif key == "--reason" and (not separator or not raw.strip() or len(raw) > 128):
                    allowed = False
    elif command == "local-mode":
        allowed = len(args) == 1 and args[0] in {"clear", "status"}
        if len(args) == 1 and args[0] == "set":
            allowed = True
        elif len(args) == 2 and args[0] == "set" and args[1].startswith("--ttl="):
            raw_ttl = args[1].partition("=")[2]
            allowed = raw_ttl.isdigit() and 60 <= int(raw_ttl) <= 86400
    elif command == "service":
        allowed = len(args) == 1 and args[0] in {"status", "start", "stop"}
    elif command == "fmu-executor":
        allowed = len(args) == 1 and args[0] in {"status", "start", "stop", "restart"}
    elif command == "artifact.read":
        allowed = len(args) == 1 and args[0] in {"heartbeat", "status", "session-events"}
    else:
        allowed = False
    if not allowed:
        raise StationCommandRejected()


def command_id() -> str:
    return str(uuid4())


__all__ = ["StationCommandResult", "StationTransport", "normalize_command_result", "validate_station_command", "command_id"]
