"""Live dependency context used by the Ops Worker composition boundaries."""

from collections.abc import Iterator, Mapping
from typing import Any


class RuntimeContext(Mapping[str, Any]):
    """Expose worker providers without allowing composition code to mutate them."""

    def __init__(self, values: Mapping[str, Any]):
        self._values = values

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)
