"""Composition adapter for request and policy input normalization."""

from typing import Any, List, Optional

from input_context import InputContext


class InputRuntime:
    """Expose input normalizers through an explicit dependency context."""

    def __init__(self, context: InputContext):
        self._context = context

    def coerce_bool(self, value: Any) -> Optional[bool]:
        return self._context.coerce_bool(value)

    def parse_bool(self, value: Any, default: bool) -> bool:
        return self._context.parse_bool(value, default)

    def normalize_args(self, args: Any, default: Optional[List[str]] = None) -> List[str]:
        return self._context.normalize_args(args, default)

    def parse_recipients(
        self,
        value: Any,
        default: Optional[List[str]] = None,
    ) -> List[str]:
        return self._context.parse_recipients(value, default)


def create_input_runtime(context: InputContext) -> InputRuntime:
    """Create an input-normalization adapter bound to explicit ports."""
    return InputRuntime(context)


__all__ = ["InputRuntime", "create_input_runtime"]
