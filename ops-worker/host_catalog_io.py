"""File and merge primitives for the static and dynamic host catalogs."""

import json
import logging
import os
from typing import Any, Dict


def read_hosts_config(path: str, missing_ok: bool = True) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        if not missing_ok:
            logging.warning("Config file %s not found, continuing with empty host list", path)
        return {"hosts": []}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"hosts": []}
    if not isinstance(data.get("hosts"), list):
        data["hosts"] = []
    return data


def merge_host_configs(
    base: Dict[str, Any],
    dynamic: Dict[str, Any],
) -> Dict[str, Any]:
    merged: Dict[str, Dict[str, Any]] = {}
    for source in (base, dynamic):
        for host in source.get("hosts", []):
            if not isinstance(host, dict):
                continue
            name = str(host.get("name") or "").strip()
            if not name:
                continue
            merged[name.lower()] = dict(host)
    return {"hosts": list(merged.values())}


__all__ = ["read_hosts_config", "merge_host_configs"]
