"""Deterministic in-memory driver used by development and CI."""

from __future__ import annotations

from threading import RLock
from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple

from power.models import PowerCapabilities

from .base import PowerDriverError


class MockPowerDriver:
    """Simulate outlet switching without contacting a physical device."""

    capabilities = PowerCapabilities(
        per_outlet_switching=True,
        read_back_state=True,
        power_cycle=True,
        delayed_actions=True,
    )

    def __init__(
        self,
        controller_id: str,
        outlets: Iterable[Tuple[str, str]],
        *,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.controller_id = controller_id
        self._defaults = {outlet_id: default_state for outlet_id, default_state in outlets}
        if not self._defaults:
            raise ValueError("mock controller requires at least one outlet")
        self.states: Dict[str, str] = dict(self._defaults)
        self._failures: Set[Tuple[str, Optional[str]]] = set()
        self._lock = RLock()
        self._sleep = sleep_fn or (lambda _seconds: None)

    def _require_outlet(self, outlet_id: str) -> str:
        outlet_id = str(outlet_id)
        if outlet_id not in self.states:
            raise PowerDriverError(f"outlet '{outlet_id}' not found")
        return outlet_id

    def _maybe_fail(self, action: str, outlet_id: str) -> None:
        if (action, outlet_id) in self._failures or (action, None) in self._failures:
            raise PowerDriverError(f"mock failure for {action} on outlet {outlet_id}")

    def fail_action(self, action: str, *, outlet: Optional[str] = None) -> None:
        self._failures.add((str(action).lower(), str(outlet) if outlet is not None else None))

    def clear_failures(self) -> None:
        self._failures.clear()

    def reset(self) -> None:
        with self._lock:
            self.states = dict(self._defaults)
            self.clear_failures()

    def discover(self) -> Dict[str, Any]:
        return {
            "reachable": True,
            "driver": "mock",
            "controllerId": self.controller_id,
            "outletCount": len(self.states),
        }

    def list_outlets(self):
        with self._lock:
            return [
                {"outlet": outlet_id, "state": state}
                for outlet_id, state in sorted(self.states.items())
            ]

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        with self._lock:
            outlet_id = self._require_outlet(outlet_id)
            return {"outlet": outlet_id, "state": self.states[outlet_id]}

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        del timeout_seconds
        state = str(state).lower()
        if state not in {"on", "off"}:
            raise PowerDriverError("mock state must be on or off")
        with self._lock:
            outlet_id = self._require_outlet(outlet_id)
            self._maybe_fail(state, outlet_id)
            self.states[outlet_id] = state
            return {"outlet": outlet_id, "state": state, "success": True}

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        del timeout_seconds
        if off_seconds <= 0:
            raise PowerDriverError("cycle off_seconds must be greater than zero")
        with self._lock:
            outlet_id = self._require_outlet(outlet_id)
            self._maybe_fail("cycle", outlet_id)
            self.states[outlet_id] = "off"
            self._sleep(off_seconds)
            self.states[outlet_id] = "on"
            return {"outlet": outlet_id, "state": "on", "success": True}
