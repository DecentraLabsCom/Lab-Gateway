"""Final composition boundary for the Ops Worker runtime surface."""

from collections.abc import Callable, MutableMapping
from typing import Any, Mapping


def compose_worker_app(
    app: Any,
    providers: MutableMapping[str, Any],
    *,
    context_factory: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    register_blueprints: Callable[[Any, Mapping[str, Any]], None],
) -> Mapping[str, Any]:
    """Register Blueprints from one live provider context.

    The composition root owns the provider namespace while each Blueprint
    receives a read-only context.  Routes are therefore exposed only through
    their Flask endpoint registrations; no duplicate module-level facades are
    published.
    """
    context = context_factory(providers)
    register_blueprints(app, context)
    return context


__all__ = ["compose_worker_app"]
