"""Composition adapter for the reservation orchestration runtime."""

from typing import Any, Optional, Protocol

from reservation_context import ReservationRuntimeContext
from reservation_orchestrator import ReservationOrchestrator as BaseReservationOrchestrator


class ReservationOrchestratorClass(Protocol):
    """Callable class surface exposed by the worker's composed orchestrator."""

    __name__: str

    def __call__(
        self,
        engine: Optional[Any],
        registry: Any,
    ) -> BaseReservationOrchestrator:
        ...


def create_reservation_orchestrator_class(
    context: ReservationRuntimeContext,
) -> ReservationOrchestratorClass:
    """Create the two-argument worker constructor over explicit dependencies."""

    class WorkerReservationOrchestrator(BaseReservationOrchestrator):
        def __init__(self, engine: Optional[Any], registry: Any):
            super().__init__(
                engine,
                registry,
                parse_bool=context.get_parse_bool(),
                get_env=context.get_env(),
                env_or_secret_file=context.get_env_or_secret_file(),
                parse_reservation_datetime=context.get_parse_reservation_datetime(),
                as_utc_datetime=context.get_as_utc_datetime(),
                http_get=context.get_http_get(),
                sql_text=context.get_sql_text(),
                bindparam=context.get_bindparam(),
                dispatch_start=context.get_dispatch_start(),
                dispatch_end=context.get_dispatch_end(),
                resolve_host_by_lab=context.get_resolve_host_by_lab(),
                record_operation=context.get_record_operation(),
                logger=context.get_logger(),
                now=context.get_now(),
            )

    WorkerReservationOrchestrator.__name__ = "ReservationOrchestrator"
    return WorkerReservationOrchestrator


__all__ = ["ReservationOrchestratorClass", "create_reservation_orchestrator_class"]
