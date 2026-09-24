"""Bounded TCP reachability probes for Guacamole-backed lab targets."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from network_probe import is_valid_ping_target


DEFAULT_PROTOCOL_PORTS = {
    "rdp": 3389,
    "vnc": 5900,
    "ssh": 22,
}
SUPPORTED_PROTOCOLS = frozenset(DEFAULT_PROTOCOL_PORTS)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _port(value: Any, default: int) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if 1 <= parsed <= 65535 else None


def normalize_lab_status_target(target: Any) -> Optional[Dict[str, Any]]:
    """Validate and normalize a target sourced from the trusted Guac catalog."""
    if not isinstance(target, Mapping):
        return None
    lab_id = str(target.get("labId") or "").strip()
    protocol = str(target.get("protocol") or "").strip().lower()
    hostname = str(target.get("hostname") or "").strip()
    if (
        not lab_id
        or protocol not in SUPPORTED_PROTOCOLS
        or not is_valid_ping_target(hostname)
    ):
        return None
    port = _port(target.get("port"), DEFAULT_PROTOCOL_PORTS[protocol])
    if port is None:
        return None
    return {
        "labId": lab_id,
        "protocol": protocol,
        "hostname": hostname,
        "port": port,
    }


class CachedLabTargetProber:
    """Probe only catalog-owned targets and cache short-lived observations."""

    def __init__(
        self,
        *,
        tcp_port_open: Callable[[str, int, float], bool],
        timeout_seconds: float,
        cache_seconds: float,
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
        max_workers: int = 8,
    ):
        self._tcp_port_open = tcp_port_open
        self._timeout_seconds = max(0.1, float(timeout_seconds))
        self._cache_seconds = max(0.0, float(cache_seconds))
        self._now = now
        self._monotonic = monotonic
        self._max_workers = max(1, int(max_workers))
        self._cache: Dict[Tuple[Any, ...], Tuple[float, Dict[str, Any]]] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _key(target: Mapping[str, Any]) -> Tuple[Any, ...]:
        return (
            str(target.get("labId") or ""),
            str(target.get("protocol") or "").lower(),
            str(target.get("hostname") or "").strip().lower(),
            target.get("port"),
        )

    def _unknown(self, reason: str) -> Dict[str, Any]:
        return {
            "signal": "unknown",
            "reason": reason,
            "source": "guacamole_tcp_probe",
            "observedAt": _iso(self._now()),
        }

    def _probe_one(self, target: Any) -> Dict[str, Any]:
        normalized = normalize_lab_status_target(target)
        if normalized is None:
            return self._unknown("target_invalid")

        key = self._key(normalized)
        current_monotonic = self._monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached and current_monotonic - cached[0] < self._cache_seconds:
                return dict(cached[1])

        try:
            reachable = bool(self._tcp_port_open(
                normalized["hostname"],
                normalized["port"],
                self._timeout_seconds,
            ))
        except Exception:  # pylint: disable=broad-except
            result = self._unknown("target_probe_error")
        else:
            result = {
                "signal": "reachable" if reachable else "unreachable",
                "reason": "target_reachable" if reachable else "target_unreachable",
                "source": "guacamole_tcp_probe",
                "observedAt": _iso(self._now()),
            }

        with self._cache_lock:
            self._cache[key] = (self._monotonic(), result)
        return dict(result)

    def probe_targets(self, targets: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Probe a bounded batch concurrently and return results keyed by lab ID."""
        unique_targets: Dict[str, Mapping[str, Any]] = {}
        for target in targets or []:
            lab_id = str(target.get("labId") or "").strip() if isinstance(target, Mapping) else ""
            if lab_id and lab_id not in unique_targets:
                unique_targets[lab_id] = target
        if not unique_targets:
            return {}

        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(unique_targets)),
            thread_name_prefix="lab-status-probe",
        ) as executor:
            futures = {
                lab_id: executor.submit(self._probe_one, target)
                for lab_id, target in unique_targets.items()
            }
            results = {}
            for lab_id, future in futures.items():
                try:
                    results[lab_id] = future.result()
                except Exception:  # pylint: disable=broad-except
                    results[lab_id] = self._unknown("target_probe_error")
            return results


__all__ = [
    "CachedLabTargetProber",
    "DEFAULT_PROTOCOL_PORTS",
    "SUPPORTED_PROTOCOLS",
    "normalize_lab_status_target",
]
