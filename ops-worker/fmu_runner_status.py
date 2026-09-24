"""Cached health projection for the active Gateway FMU runner."""

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CachedFmuRunnerStatus:
    """Read the internal runner health endpoint without blocking public status."""

    def __init__(
        self,
        *,
        http_get: Callable[..., Any],
        url: str,
        timeout_seconds: float,
        cache_seconds: float,
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
    ):
        self._http_get = http_get
        self._url = str(url or "").strip()
        self._timeout_seconds = max(0.2, float(timeout_seconds))
        self._cache_seconds = max(0.0, float(cache_seconds))
        self._now = now
        self._monotonic = monotonic
        self._cache: Optional[Tuple[float, Dict[str, str]]] = None
        self._cache_lock = Lock()

    def _unknown(self) -> Dict[str, str]:
        return {
            "signal": "unknown",
            "reason": "fmu_runner_unavailable",
            "source": "fmu_runner_health",
            "observedAt": _iso(self._now()),
        }

    def _read(self) -> Dict[str, str]:
        observed_at = _iso(self._now())
        if not self._url:
            return self._unknown()
        try:
            response = self._http_get(
                self._url,
                headers={"Accept": "application/json"},
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
            payload = response.json()
        except Exception:  # pylint: disable=broad-except
            return self._unknown()

        if not isinstance(payload, Mapping):
            return self._unknown()
        backend_mode = str(payload.get("backendMode") or "").strip().lower()
        status = str(payload.get("status") or "").strip().upper()
        raw_fmu_count = payload.get("fmuCount")
        try:
            fmu_count = int(str(raw_fmu_count)) if raw_fmu_count is not None else 0
        except (TypeError, ValueError):
            fmu_count = 0

        if backend_mode not in {"local", "station"}:
            return {
                "signal": "unknown",
                "reason": "fmu_runner_unavailable",
                "source": "fmu_runner_health",
                "observedAt": observed_at,
            }
        if status == "UP" and fmu_count > 0:
            signal = "ready"
            reason = "fmu_ready"
        elif status in {"UP", "DEGRADED", "DOWN"}:
            signal = "not_ready"
            reason = "fmu_not_ready"
        else:
            signal = "unknown"
            reason = "fmu_runner_unavailable"
        return {
            "signal": signal,
            "reason": reason,
            "source": "fmu_runner_health",
            "observedAt": observed_at,
        }

    def get_status(self) -> Dict[str, str]:
        current = self._monotonic()
        with self._cache_lock:
            if self._cache and current - self._cache[0] < self._cache_seconds:
                return dict(self._cache[1])

        result = self._read()
        with self._cache_lock:
            self._cache = (self._monotonic(), result)
        return dict(result)


__all__ = ["CachedFmuRunnerStatus"]
