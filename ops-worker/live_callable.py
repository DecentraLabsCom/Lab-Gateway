"""Late-bound callable adapters for the worker's mutable provider namespace."""

from collections.abc import Mapping
from typing import Any


class LiveCallable:
    """Resolve a worker dependency at call time, preserving runtime patch points."""

    __slots__ = ("_namespace", "_path")

    def __init__(self, namespace: Mapping[str, Any], path: str):
        self._namespace = namespace
        self._path = tuple(path.split("."))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        target: Any = self._namespace[self._path[0]]
        for name in self._path[1:]:
            target = getattr(target, name)
        return target(*args, **kwargs)


__all__ = ["LiveCallable"]
