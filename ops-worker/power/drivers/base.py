"""Small common interface shared by power controller drivers."""

from typing import Any, Dict, List, Protocol

from power.models import PowerCapabilities


class PowerDriverError(RuntimeError):
    """Raised when a controller cannot complete an operation."""


class PowerDriver(Protocol):
    capabilities: PowerCapabilities

    def discover(self) -> Dict[str, Any]:
        ...

    def list_outlets(self) -> List[Dict[str, Any]]:
        ...

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        ...

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        ...

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        ...
