"""Host catalog reload orchestration with explicit dependencies."""

from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple


def reload_hosts(
    *,
    load_config: Callable[[], Dict[str, Any]],
    registry_factory: Callable[[Dict[str, Any]], Any],
    refresh_trust_store: Callable[[Any], Any],
    replace_registry: Callable[[Any], None],
    logger: Any,
) -> Tuple[int, Optional[str]]:
    """Load, trust-refresh and atomically publish a new host registry."""
    try:
        config = load_config()
        registry = registry_factory(config)
        refresh_trust_store(registry.all_hosts())
        replace_registry(registry)
        logger.info("Reloaded hosts catalog (%s hosts)", registry.count())
        return registry.count(), None
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to reload hosts: %s", exc)
        return 0, "Host catalog reload failed"
