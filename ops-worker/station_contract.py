"""Single ingress normalizer for Windows v2 and platform-neutral Station v3."""

from datetime import datetime, timezone
from typing import Any, Dict, Mapping


class StationContractError(ValueError):
    """Raised when a station payload is malformed or uses an unsupported major."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StationContractError(f"{field} must be an object")
    return value


def _capability(value: Any, field: str) -> Dict[str, Any]:
    item = _mapping(value, field)
    available = item.get("available", False)
    ready = item.get("ready", False)
    issues = item.get("issues", [])
    if not isinstance(available, bool) or not isinstance(ready, bool):
        raise StationContractError(f"{field}.available and {field}.ready must be booleans")
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        raise StationContractError(f"{field}.issues must be a string array")
    return {
        **dict(item),
        "available": available,
        "ready": ready,
        "issues": issues,
    }


def _version_major(payload: Mapping[str, Any]) -> int:
    version = str(payload.get("schemaVersion") or "")
    try:
        return int(version.split(".", 1)[0])
    except (TypeError, ValueError) as exc:
        raise StationContractError("schemaVersion is missing or invalid") from exc


def normalize_station_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the supported envelope and map it to one internal shape.

    The input is retained byte-for-byte by the caller for raw persistence. The
    returned projection contains no inferred platform-specific fields.
    """
    root = _mapping(payload, "station payload")
    major = _version_major(root)
    if major == 2:
        return _normalize_windows_v2(root)
    if major != 3:
        raise StationContractError(f"Station Contract major {major} is unsupported")
    return _normalize_v3(root)


def _normalize_windows_v2(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate the existing Windows status or heartbeat envelope."""
    status = payload.get("status")
    if not isinstance(status, Mapping):
        status = payload
    readiness = _mapping(status.get("readiness", {}), "readiness")
    sessions = _mapping(status.get("sessions", {}), "sessions")
    summary = _mapping(status.get("summary", {}), "summary")
    winrm = _mapping(status.get("winrm", {}), "winrm")
    profile = str(status.get("stationProfile") or "server")
    if profile == "server":
        profile = "dedicated"
    if profile not in {"dedicated", "hybrid"}:
        profile = "dedicated"
    stamp = payload.get("timestamp") or status.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError as exc:
        raise StationContractError("timestamp is missing or invalid") from exc
    if timestamp.tzinfo is None:
        raise StationContractError("timestamp must include a timezone")
    physical = _capability(readiness.get("physicalLab", {}), "readiness.physicalLab")
    wake = _capability(readiness.get("wake", {}), "readiness.wake")
    fmu = _capability(readiness.get("fmu", {}), "readiness.fmu")
    local_active = bool(status.get("localSessionActive", sessions.get("localSessionActive", False)))
    return {
        "contractVersion": str(status.get("schemaVersion") or payload.get("schemaVersion")),
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "host": str(payload.get("host") or status.get("host") or ""),
        "version": str(payload.get("version") or status.get("version") or ""),
        "platform": {"os": "windows"},
        "profile": profile,
        "management": {"transport": "winrm", "ready": bool(winrm.get("ready", False))},
        "remoteAccess": {
            "mode": "remote-app",
            "ready": bool(status.get("remoteAppEnabled", payload.get("remoteAppEnabled", False))),
        },
        "readiness": {"physicalLab": physical, "wake": wake, "fmu": fmu},
        "sessions": {**dict(sessions), "localSessionActive": local_active},
        "summary": dict(summary),
        "operations": dict(status.get("operations", payload.get("operations", {})) or {}),
        "localModeEnabled": bool(status.get("localModeEnabled", False)),
        "rawSchemaVersion": str(payload.get("schemaVersion") or ""),
    }


def _normalize_v3(payload: Mapping[str, Any]) -> Dict[str, Any]:
    required = ("timestamp", "host", "version", "platform", "profile", "management", "remoteAccess", "summary", "readiness", "sessions", "operations", "localModeEnabled")
    missing = [field for field in required if field not in payload]
    if missing:
        raise StationContractError("Station Contract v3 is missing: " + ", ".join(missing))
    platform = _mapping(payload["platform"], "platform")
    if platform.get("os") not in {"linux", "windows"}:
        raise StationContractError("platform.os must be linux or windows")
    management = _mapping(payload["management"], "management")
    transport = management.get("transport")
    if transport not in {"ssh", "winrm"}:
        raise StationContractError("management.transport is unsupported")
    expected_transport = "ssh" if platform.get("os") == "linux" else "winrm"
    if transport != expected_transport:
        raise StationContractError(f"management.transport must be {expected_transport} for {platform.get('os')}")
    if not isinstance(management.get("ready"), bool):
        raise StationContractError("management.ready must be a boolean")
    remote = _mapping(payload["remoteAccess"], "remoteAccess")
    readiness = _mapping(payload["readiness"], "readiness")
    summary = _mapping(payload["summary"], "summary")
    sessions = _mapping(payload["sessions"], "sessions")
    if payload["profile"] not in {"dedicated", "hybrid", "fmu-only"}:
        raise StationContractError("profile is unsupported")
    if not isinstance(payload["localModeEnabled"], bool):
        raise StationContractError("localModeEnabled must be a boolean")
    if not isinstance(sessions.get("active"), list) or not isinstance(sessions.get("localSessionActive"), bool):
        raise StationContractError("sessions.active and sessions.localSessionActive are required")
    if not isinstance(summary.get("ready"), bool) or not isinstance(summary.get("issues"), list):
        raise StationContractError("summary.ready and summary.issues are required and must be typed")
    if any(not isinstance(issue, str) for issue in summary["issues"]):
        raise StationContractError("summary.issues must be a string array")
    if not isinstance(remote.get("mode"), str) or not isinstance(remote.get("ready"), bool):
        raise StationContractError("remoteAccess.mode and remoteAccess.ready are required and must be typed")
    try:
        timestamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise StationContractError("timestamp is invalid") from exc
    if timestamp.tzinfo is None:
        raise StationContractError("timestamp must include a timezone")
    normalized_readiness = {
        key: _capability(readiness.get(key, {}), f"readiness.{key}")
        for key in ("physicalLab", "wake", "fmu")
    }
    if "remoteAccess" in readiness:
        normalized_readiness["remoteAccess"] = _capability(readiness["remoteAccess"], "readiness.remoteAccess")
    return {
        "contractVersion": "3.0.0",
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "host": str(payload["host"]),
        "version": str(payload["version"]),
        "platform": dict(platform),
        "profile": str(payload["profile"]),
        "management": dict(management),
        "remoteAccess": dict(remote),
        "readiness": normalized_readiness,
        "sessions": dict(sessions),
        "summary": dict(summary),
        "operations": dict(_mapping(payload["operations"], "operations")),
        "localModeEnabled": payload["localModeEnabled"],
        "rawSchemaVersion": "3.0.0",
    }


__all__ = ["StationContractError", "normalize_station_payload"]
