"""Pure heartbeat values and Wake-on-LAN hint selection."""

import re
from collections.abc import Callable, Mapping
from typing import Any, Dict, List, Optional, Pattern, Tuple


MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")


def normalize_mac(value: Any, *, mac_pattern: Pattern[str] = MAC_RE) -> str:
    candidate = str(value or "").strip()
    if not mac_pattern.fullmatch(candidate):
        return ""
    return candidate.replace("-", ":").upper()


def parse_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled", "up"}


def extract_nic_candidates_from_heartbeat(
    heartbeat: Mapping[str, Any],
    *,
    normalize_mac_fn: Callable[[Any], str] = normalize_mac,
    parse_boolish_fn: Callable[[Any], bool] = parse_boolish,
) -> List[Dict[str, Any]]:
    raw_status = heartbeat.get("status")
    status = raw_status if isinstance(raw_status, dict) else heartbeat
    raw_wake = status.get("wake")
    wake = raw_wake if isinstance(raw_wake, dict) else {}
    raw_adapters = wake.get("nicPower")
    adapters = raw_adapters if isinstance(raw_adapters, list) else []
    candidates = []
    for adapter in adapters:
        if not isinstance(adapter, dict):
            continue
        mac = normalize_mac_fn(
            adapter.get("macAddress")
            or adapter.get("mac")
            or adapter.get("physicalAddress")
        )
        if not mac:
            continue
        candidates.append({
            "mac": mac,
            "name": adapter.get("name") or adapter.get("interfaceAlias") or "",
            "status": adapter.get("status") or "",
            "wolReady": parse_boolish_fn(adapter.get("wolReady")),
            "wakeArmed": parse_boolish_fn(adapter.get("wakeArmed")),
        })
    return candidates


def choose_wol_mac(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    def score(candidate: Dict[str, Any]) -> Tuple[int, int, int]:
        status = str(candidate.get("status") or "").strip().lower()
        return (
            1 if candidate.get("wolReady") else 0,
            1 if status == "up" else 0,
            1 if candidate.get("wakeArmed") else 0,
        )

    best = sorted(candidates, key=score, reverse=True)[0]
    return {"mac": best["mac"], "source": "status.wake.nicPower", "adapter": best}


def suggest_mac_from_heartbeat(
    heartbeat: Mapping[str, Any],
    *,
    normalize_mac_fn: Callable[[Any], str] = normalize_mac,
    parse_boolish_fn: Callable[[Any], bool] = parse_boolish,
) -> Optional[Dict[str, Any]]:
    return choose_wol_mac(
        extract_nic_candidates_from_heartbeat(
            heartbeat,
            normalize_mac_fn=normalize_mac_fn,
            parse_boolish_fn=parse_boolish_fn,
        )
    )
