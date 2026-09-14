"""Host catalog loading orchestration with explicit dependencies."""

import os

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Protocol, Tuple


class ConfigReader(Protocol):
    """Callable shape for readers supporting the optional-file flag."""

    def __call__(self, path: str, missing_ok: bool = True) -> Dict[str, Any]:
        ...


__all__ = [
    "ConfigReader",
    "load_dynamic_config",
    "load_host_config",
    "resolve_host_secret_refs",
    "update_dynamic_host",
    "upsert_dynamic_host",
    "write_dynamic_config",
]


def resolve_host_secret_refs(
    raw: Dict[str, Any],
    *,
    credential_ref_for_host: Callable[[Any], str],
    credentials_configured: Callable[[str], bool],
    warn: Callable[..., Any],
) -> Dict[str, Any]:
    """Normalize host credential references without copying secret material."""
    for host in raw.get("hosts", []):
        if not host.get("credential_ref"):
            host["credential_ref"] = host.get("address") or host.get("name")
        host.pop("winrm_user", None)
        host.pop("winrm_pass", None)
        if not credentials_configured(credential_ref_for_host(host)):
            warn("Missing WinRM credentials for host %s", host.get("name", "<unknown>"))
    return raw


def load_dynamic_config(
    dynamic_config_path: str,
    *,
    read_config: ConfigReader,
) -> Dict[str, Any]:
    """Load the optional dynamic host catalog."""
    return read_config(dynamic_config_path, missing_ok=True)


def load_host_config(
    config_path: str,
    dynamic_config_path: str,
    *,
    read_config: ConfigReader,
    merge_configs: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    validate_config: Callable[[Dict[str, Any]], None],
    resolve_secret_refs: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Load, merge and validate the static and dynamic host catalogs."""
    base = read_config(config_path, missing_ok=False)
    dynamic = read_config(dynamic_config_path, missing_ok=True)
    merged = merge_configs(base, dynamic)
    validate_config(merged)
    return resolve_secret_refs(merged)


def write_dynamic_config(
    config: Dict[str, Any],
    dynamic_config_path: str,
    *,
    path_dirname: Callable[[str], str],
    make_dirs: Callable[..., Any],
    open_file: Callable[..., Any],
    dump_json: Callable[..., Any],
    replace_file: Callable[[str, str], Any],
) -> None:
    """Persist the dynamic host catalog through an atomic file replacement."""
    directory = path_dirname(dynamic_config_path) or "."
    make_dirs(directory, exist_ok=True)
    tmp_path = f"{dynamic_config_path}.tmp"
    with open_file(tmp_path, "w", encoding="utf-8") as handle:
        dump_json(config, handle, indent=2)
        handle.write("\n")
    replace_file(tmp_path, dynamic_config_path)


def upsert_dynamic_host(
    host_config: Dict[str, Any],
    *,
    load_config: Callable[[], Dict[str, Any]],
    write_config: Callable[[Dict[str, Any]], None],
) -> None:
    """Replace a dynamic host by name or append it to the catalog."""
    config = load_config()
    hosts = [host for host in config.get("hosts", []) if isinstance(host, dict)]
    key = str(host_config.get("name") or "").strip().lower()
    replaced = False
    for index, host in enumerate(hosts):
        if str(host.get("name") or "").strip().lower() == key:
            hosts[index] = host_config
            replaced = True
            break
    if not replaced:
        hosts.append(host_config)
    config["hosts"] = hosts
    write_config(config)


def update_dynamic_host(
    host_name: str,
    payload: Dict[str, Any],
    *,
    load_config: Callable[[], Dict[str, Any]],
    write_config: Callable[[Dict[str, Any]], None],
    normalize_key: Callable[[Any], str],
    sanitize_name: Callable[[Any, Optional[Any]], Tuple[Optional[str], Optional[str]]],
    normalize_mac: Callable[[Any], Optional[str]],
    host_get: Callable[[str], Optional[Dict[str, Any]]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Update editable dynamic host fields while preserving other settings."""
    config = load_config()
    hosts: List[Dict[str, Any]] = [
        host for host in config.get("hosts", []) if isinstance(host, dict)
    ]
    original_key = normalize_key(host_name)
    host_index = next(
        (
            index for index, host in enumerate(hosts)
            if normalize_key(host.get("name")) == original_key
        ),
        None,
    )
    if host_index is None:
        return None, "host is defined in the static catalog; edit ops-worker/hosts.json manually"

    current = dict(hosts[host_index])
    name, error = sanitize_name(payload.get("name"), current.get("name"))
    if error or name is None:
        return None, error or "host name is required"
    if normalize_key(name) != original_key:
        existing = host_get(name)
        if existing and normalize_key(existing.get("name")) != original_key:
            return None, f"host {name} already exists"

    updated = dict(current)
    updated["name"] = name

    if "mac" in payload:
        raw_mac = str(payload.get("mac") or "").strip()
        if raw_mac:
            mac = normalize_mac(raw_mac)
            if not mac:
                return None, "mac must use format 00:11:22:33:44:55 or 00-11-22-33-44-55"
            updated["mac"] = mac
        else:
            updated.pop("mac", None)

    if "heartbeatPath" in payload:
        heartbeat_path = str(payload.get("heartbeatPath") or "").strip()
        if not heartbeat_path:
            return None, "heartbeatPath is required"
        if len(heartbeat_path) > 1024 or any(ord(char) < 32 for char in heartbeat_path):
            return None, "heartbeatPath must be a valid Windows path"
        updated["heartbeat_path"] = heartbeat_path

    hosts[host_index] = updated
    config["hosts"] = hosts
    write_config(config)
    return updated, None
