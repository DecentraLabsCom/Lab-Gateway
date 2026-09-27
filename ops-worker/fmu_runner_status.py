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
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _non_negative_int(value: Any) -> Optional[int]:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _unknown(self) -> Dict[str, Any]:
        return {
            "signal": "unknown",
            "reason": "fmu_runner_unavailable",
            "source": "fmu_runner_health",
            "observedAt": _iso(self._now()),
            "capacity": {
                "state": "unknown",
                "active": None,
                "maximum": None,
                "available": None,
            },
        }

    def _read_capacity(
        self,
        payload: Mapping[str, Any],
        *,
        signal_hint: str = "",
    ) -> Dict[str, Any]:
        nested = payload.get("capacity")
        nested = nested if isinstance(nested, Mapping) else {}
        active = self._non_negative_int(
            payload.get("activeExecutions", nested.get("active"))
        )
        maximum = self._non_negative_int(
            payload.get("maxConcurrentExecutions", nested.get("maximum"))
        )
        available = self._non_negative_int(
            payload.get("availableCapacity", nested.get("available"))
        )
        if available is None and active is not None and maximum is not None:
            available = max(0, maximum - active)

        if signal_hint == "busy" or available == 0:
            state = "busy"
        elif available is not None and available > 0:
            state = "available"
        else:
            state = "unknown"
        return {
            "state": state,
            "active": active,
            "maximum": maximum,
            "available": available,
        }

    def _read(self, lab_id: Optional[str] = None) -> Dict[str, Any]:
        observed_at = _iso(self._now())
        if not self._url:
            return self._unknown()
        try:
            request_kwargs = {
                "headers": {"Accept": "application/json"},
                "timeout": self._timeout_seconds,
                "allow_redirects": False,
            }
            if lab_id:
                request_kwargs["params"] = {"labId": str(lab_id)}
            response = self._http_get(
                self._url,
                **request_kwargs,
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
            return self._unknown()
        if status == "UP" and fmu_count > 0:
            capacity = self._read_capacity(payload)
            if capacity["state"] == "busy":
                signal = "busy"
                reason = "fmu_capacity_exhausted"
            else:
                signal = "ready"
                reason = "fmu_ready"
        elif status in {"UP", "DEGRADED", "DOWN"}:
            signal = "not_ready"
            reason = "fmu_not_ready"
            capacity = self._read_capacity(payload)
        else:
            signal = "unknown"
            reason = "fmu_runner_unavailable"
            capacity = self._read_capacity(payload)
        return {
            "signal": signal,
            "reason": reason,
            "source": "fmu_runner_health",
            "observedAt": observed_at,
            "capacity": capacity,
        }

    def get_status(self, lab_id: Optional[str] = None) -> Dict[str, Any]:
        cache_key = str(lab_id or "")
        current = self._monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and current - cached[0] < self._cache_seconds:
                return dict(cached[1])

        result = self._read(lab_id)
        with self._cache_lock:
            self._cache[cache_key] = (self._monotonic(), result)
        return dict(result)


__all__ = ["CachedFmuRunnerStatus"]
