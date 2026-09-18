"""Canonical Lab Station artifact paths and per-host path resolution."""

from pathlib import PureWindowsPath
from typing import Any, Dict, Optional


DEFAULT_LABSTATION_ROOT = r"C:\Lab Station"

_PATH_KEYS = (
    "labstation_exe",
    "local_mode_flag_path",
    "heartbeat_path",
    "events_path",
)


def _as_windows_path(value: Any) -> Optional[PureWindowsPath]:
    raw = str(value or "").strip()
    if not raw:
        return None
    return PureWindowsPath(raw)


def _path_text(path: PureWindowsPath) -> str:
    return str(path)


def paths_for_root(root: Any) -> Dict[str, str]:
    """Build the four Lab Station paths for one installation root."""
    root_path = _as_windows_path(root) or PureWindowsPath(DEFAULT_LABSTATION_ROOT)
    station_dir = root_path / "labstation"
    telemetry_dir = station_dir / "data" / "telemetry"
    return {
        "labstation_exe": _path_text(root_path / "LabStation.exe"),
        "local_mode_flag_path": _path_text(station_dir / "data" / "local-mode.flag"),
        "heartbeat_path": _path_text(telemetry_dir / "heartbeat.json"),
        "events_path": _path_text(telemetry_dir / "session-guard-events.jsonl"),
    }


def root_from_executable(value: Any) -> Optional[PureWindowsPath]:
    """Return the installation root represented by a LabStation executable."""
    path = _as_windows_path(value)
    if path is None or path.name.casefold() != "labstation.exe":
        return None
    return path.parent


def root_from_heartbeat(value: Any) -> Optional[PureWindowsPath]:
    """Return the installation root represented by a standard heartbeat path."""
    path = _as_windows_path(value)
    if path is None or path.name.casefold() != "heartbeat.json":
        return None
    station_dir = path.parent.parent.parent
    if station_dir.name.casefold() != "labstation":
        return None
    return station_dir.parent


def _belongs_to_root(value: Any, root: PureWindowsPath) -> bool:
    path = _as_windows_path(value)
    if path is None:
        return False
    root_text = _path_text(root).rstrip("\\/").casefold()
    path_text = _path_text(path).casefold()
    return path_text == root_text or path_text.startswith(root_text + "\\")


def resolve_labstation_paths(host: Dict[str, Any]) -> Dict[str, str]:
    """Resolve a coherent set of Lab Station paths for a host.

    Explicit paths are preserved when they belong to the same installation
    root. If a partially configured host mixes roots, the heartbeat path (or
    executable, when available) identifies the root and the remaining paths
    are derived from it. This repairs legacy catalogs that contain a real
    spaced heartbeat path together with old no-space defaults.
    """
    configured_executable = host.get("labstation_exe")
    configured_heartbeat = host.get("heartbeat_path")
    root = root_from_executable(configured_executable)
    root_source = "executable" if root is not None else ""
    if root is None:
        root = root_from_heartbeat(configured_heartbeat)
        root_source = "heartbeat" if root is not None else ""
    if root is None:
        root = PureWindowsPath(DEFAULT_LABSTATION_ROOT)
        root_source = "default"

    derived = paths_for_root(root)
    resolved: Dict[str, str] = {}
    for key in _PATH_KEYS:
        configured = host.get(key)
        if not configured:
            resolved[key] = derived[key]
        elif root_source == "default":
            # Preserve explicitly configured non-standard paths. There is no
            # reliable installation root from which to rewrite them.
            resolved[key] = str(configured).strip()
        elif key == "heartbeat_path" and root_source == "heartbeat":
            resolved[key] = str(configured).strip()
        elif _belongs_to_root(configured, root):
            resolved[key] = str(configured).strip()
        else:
            resolved[key] = derived[key]
    return resolved


__all__ = [
    "DEFAULT_LABSTATION_ROOT",
    "paths_for_root",
    "resolve_labstation_paths",
    "root_from_executable",
    "root_from_heartbeat",
]
