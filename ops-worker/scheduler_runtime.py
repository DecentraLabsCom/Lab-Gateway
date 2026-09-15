"""Composition adapter for Ops Worker scheduler startup."""

from typing import Any

from scheduler_context import SchedulerContext


class SchedulerRuntime:
    """Expose scheduler startup through explicit configuration providers."""

    def __init__(self, context: SchedulerContext):
        self._context = context

    def start_scheduler(self) -> None:
        context = self._context
        return context.get_start_scheduler()(
            scheduler_factory=context.get_scheduler_factory(),
            poll_enabled=context.get_poll_enabled(),
            poll_interval_seconds=context.get_poll_interval_seconds(),
            poll_all_hosts=context.get_poll_all_hosts(),
            register_reservation_jobs=context.get_register_reservation_jobs(),
            cleanup_enabled=context.get_cleanup_enabled(),
            cleanup_interval_seconds=context.get_cleanup_interval_seconds(),
            cleanup_expired_users=context.get_cleanup_expired_users(),
            observation_enabled=context.get_observation_enabled(),
            observation_interval_seconds=context.get_observation_interval_seconds(),
            deliver_observations=context.get_deliver_observations(),
            revocation_interval_seconds=context.get_revocation_interval_seconds(),
            process_revocations=context.get_process_revocations(),
            now=context.get_now(),
            logger=context.get_logger(),
        )


def create_scheduler_runtime(context: SchedulerContext) -> SchedulerRuntime:
    """Create a scheduler runtime bound to explicit providers."""
    return SchedulerRuntime(context)


__all__ = ["SchedulerRuntime", "create_scheduler_runtime"]
