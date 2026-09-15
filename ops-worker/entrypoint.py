"""Process startup orchestration for the Ops Worker."""

from collections.abc import Callable, Sequence
from typing import Any


def configure_logging(
    *,
    level: str,
    basic_config: Callable[..., Any],
) -> None:
    """Configure process logging without importing the application composition."""
    basic_config(
        level=str(level or "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def run(
    *,
    configure_logging: Callable[[], Any],
    refresh_trust_store: Callable[[Sequence[dict[str, Any]]], Any],
    hosts: Sequence[dict[str, Any]],
    start_scheduler: Callable[[], Any],
    bind: str,
    port: int,
    serve: Callable[..., Any],
    app: Any,
) -> Any:
    """Run the worker startup sequence and hand the app to Waitress."""
    configure_logging()
    refresh_trust_store(hosts)
    scheduler = start_scheduler()
    try:
        return serve(app, host=bind, port=port)
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=True)


__all__ = ["configure_logging", "run"]
