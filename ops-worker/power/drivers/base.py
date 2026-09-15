"""Small common interface shared by power controller drivers."""

from typing import Any, Dict, List, Mapping, Protocol

from power.models import PowerCapabilities


class PowerDriverError(RuntimeError):
    """Raised when a controller cannot complete an operation."""


class PowerDriver(Protocol):
    capabilities: PowerCapabilities

    def discover(self) -> Dict[str, Any]:
        raise NotImplementedError

    def list_outlets(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def read_configuration(self) -> Dict[str, Any]:
        """Read the physical controller/output configuration."""
        raise NotImplementedError

    def apply_configuration(self, configuration: Mapping[str, Any]) -> Dict[str, Any]:
        """Apply supported physical configuration and return the read-back state."""
        raise NotImplementedError

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        raise NotImplementedError

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        raise NotImplementedError
