"""Compatibility construction for the reservation orchestration runtime."""

from collections.abc import Mapping
from typing import Any, Optional, Type

from reservation_orchestrator import ReservationOrchestrator as BaseReservationOrchestrator


def create_reservation_orchestrator_class(
    providers: Mapping[str, Any],
) -> Type[BaseReservationOrchestrator]:
    """Create the legacy two-argument adapter over the explicit orchestrator.

    Provider lookups remain live so tests and runtime reloads can replace the
    historical worker-level callbacks without importing this module again.
    """
    get = providers.__getitem__

    class WorkerReservationOrchestrator(BaseReservationOrchestrator):
        def __init__(self, engine: Optional[Any], registry: Any):
            super().__init__(
                engine,
                registry,
                parse_bool=get("parse_bool"),
                get_env=get("os").getenv,
                env_or_secret_file=lambda name: get("_env_or_secret_file")(name),
                parse_reservation_datetime=get("_parse_reservation_datetime"),
                as_utc_datetime=get("_as_utc_datetime"),
                http_get=lambda *args, **kwargs: get("requests").get(*args, **kwargs),
                sql_text=get("text"),
                bindparam=get("bindparam"),
                dispatch_start=lambda payload: get("handle_reservation_start")(payload),
                dispatch_end=lambda payload: get("handle_reservation_end")(payload),
                record_operation=lambda *args, **kwargs: get(
                    "record_reservation_operation"
                )(*args, **kwargs),
                logger=get("logging"),
                now=lambda: get("datetime").now(get("timezone").utc),
            )

    WorkerReservationOrchestrator.__name__ = "ReservationOrchestrator"
    return WorkerReservationOrchestrator


__all__ = ["create_reservation_orchestrator_class"]
