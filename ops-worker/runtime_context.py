"""Live dependency context used by the Ops Worker composition boundaries."""

from collections.abc import Iterator, Mapping
from typing import Any, Optional


class RuntimeContext(Mapping[str, Any]):
    """Expose worker providers without allowing composition code to mutate them."""

    def __init__(
        self,
        values: Mapping[str, Any],
        *,
        fallbacks: Optional[Mapping[str, Any]] = None,
    ):
        self._values = values
        self._fallbacks = fallbacks or {}

    def __getitem__(self, key: str) -> Any:
        try:
            return self._values[key]
        except KeyError:
            return self._fallbacks[key]

    def __iter__(self) -> Iterator[str]:
        yield from self._values
        yield from (key for key in self._fallbacks if key not in self._values)

    def __len__(self) -> int:
        return len(self._values) + sum(key not in self._values for key in self._fallbacks)
