"""Final composition boundary for the Ops Worker runtime surface."""

from collections.abc import Callable, MutableMapping
from typing import Any, Mapping, Tuple


def compose_worker_app(
    app: Any,
    providers: MutableMapping[str, Any],
    *,
    context_factory: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    legacy_factory: Callable[[Mapping[str, Any]], Mapping[str, Callable[..., Any]]],
    register_blueprints: Callable[[Any, Mapping[str, Any]], None],
) -> Tuple[Mapping[str, Any], Mapping[str, Callable[..., Any]]]:
    """Publish legacy facades and Blueprints from one live provider context.

    The order intentionally mirrors the historical composition in ``worker``:
    create the live context, build facades against it, publish those facades to
    the worker namespace, and only then register the Blueprints.
    """
    context = context_factory(providers)
    legacy = legacy_factory(context)
    providers.update(legacy)
    register_blueprints(app, context)
    return context, legacy


__all__ = ["compose_worker_app"]
