"""Late-bound callable adapters for the worker's mutable provider namespace."""

from collections.abc import Mapping
from typing import Any


class LiveCallable:
    """Resolve a worker dependency at call time, preserving runtime patch points."""

    __slots__ = ("_namespace", "_path", "_default_target")

    def __init__(self, namespace: Mapping[str, Any], path: str, default_target: Any):
        self._namespace = namespace
        self._path = tuple(path.split("."))
        self._default_target = default_target

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        target: Any = self._namespace.get(self._path[0], self._default_target)
        for name in self._path[1:]:
            try:
                target = getattr(target, name)
            except AttributeError:
                target = self._default_target
                break
        return target(*args, **kwargs)


__all__ = ["LiveCallable"]
