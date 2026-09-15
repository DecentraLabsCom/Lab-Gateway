"""Explicit dependencies for Ops Worker scheduler startup."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchedulerContext:
    """Scheduler service, job callbacks and configuration providers."""

    get_start_scheduler: Callable[[], Callable[..., Any]]
    get_scheduler_factory: Callable[[], Callable[[], Any]]
    get_poll_enabled: Callable[[], bool]
    get_poll_interval_seconds: Callable[[], int]
    get_poll_all_hosts: Callable[[], Any]
    get_register_reservation_jobs: Callable[[], Any]
    get_cleanup_enabled: Callable[[], bool]
    get_cleanup_interval_seconds: Callable[[], int]
    get_cleanup_expired_users: Callable[[], Any]
    get_observation_enabled: Callable[[], bool]
    get_observation_interval_seconds: Callable[[], int]
    get_deliver_observations: Callable[[], Any]
    get_revocation_interval_seconds: Callable[[], int]
    get_process_revocations: Callable[[], Any]
    get_now: Callable[[], Callable[[], Any]]
    get_logger: Callable[[], Any]


__all__ = ["SchedulerContext"]
