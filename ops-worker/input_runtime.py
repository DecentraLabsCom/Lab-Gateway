"""Composition adapter for request and policy input normalization."""

from collections.abc import Mapping
from typing import Any, List, Optional


class InputRuntime:
    """Resolve input normalizers from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def coerce_bool(self, value: Any) -> Optional[bool]:
        return self._get("_coerce_bool_impl")(value)

    def parse_bool(self, value: Any, default: bool) -> bool:
        return self._get("_parse_bool_impl")(value, default)

    def normalize_args(self, args: Any, default: Optional[List[str]] = None) -> List[str]:
        return self._get("_normalize_args_impl")(args, default)

    def parse_recipients(
        self,
        value: Any,
        default: Optional[List[str]] = None,
    ) -> List[str]:
        return self._get("_parse_recipients_impl")(value, default)


def create_input_runtime(providers: Mapping[str, Any]) -> InputRuntime:
    """Create an input-normalization adapter bound to live providers."""
    return InputRuntime(providers)


__all__ = ["InputRuntime", "create_input_runtime"]
