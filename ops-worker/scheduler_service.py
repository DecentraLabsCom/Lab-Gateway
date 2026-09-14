"""Scheduler job registration for the Ops Worker."""

from typing import Any, Callable


def start_scheduler(
    *,
    scheduler_factory: Callable[[], Any],
    poll_enabled: bool,
    poll_interval_seconds: int,
    poll_all_hosts: Callable[[], Any],
    register_reservation_jobs: Callable[[Any], int],
    cleanup_enabled: bool,
    cleanup_interval_seconds: int,
    cleanup_expired_users: Callable[[], Any],
    observation_enabled: bool,
    observation_interval_seconds: int,
    deliver_observations: Callable[[], Any],
    revocation_interval_seconds: int,
    process_revocations: Callable[[], Any],
    now: Callable[[], Any],
    logger: Any,
) -> None:
    """Register enabled jobs and start the scheduler when work is present."""
    scheduler = scheduler_factory()
    jobs = 0

    if poll_enabled:
        scheduler.add_job(
            poll_all_hosts,
            "interval",
            seconds=poll_interval_seconds,
            next_run_time=now(),
            id="heartbeat-poller",
            replace_existing=True,
        )
        jobs += 1
        logger.info("Heartbeat poller enabled (interval %ss)", poll_interval_seconds)

    jobs += register_reservation_jobs(scheduler)

    if cleanup_enabled:
        scheduler.add_job(
            cleanup_expired_users,
            "interval",
            seconds=cleanup_interval_seconds,
            next_run_time=now(),
            id="guacamole-temp-user-cleanup",
            replace_existing=True,
        )
        jobs += 1
        logger.info(
            "Guacamole temporary user cleanup enabled (interval %ss)",
            cleanup_interval_seconds,
        )

    if observation_enabled:
        scheduler.add_job(
            deliver_observations,
            "interval",
            seconds=observation_interval_seconds,
            next_run_time=now(),
            id="session-observation-outbox",
            replace_existing=True,
        )
        jobs += 1
        logger.info(
            "Session observation outbox enabled (interval %ss)",
            observation_interval_seconds,
        )

    scheduler.add_job(
        process_revocations,
        "interval",
        seconds=revocation_interval_seconds,
        next_run_time=now(),
        id="guacamole-token-revocation",
        replace_existing=True,
    )
    jobs += 1
    logger.info(
        "Durable Guacamole token revocation enabled (interval %ss)",
        revocation_interval_seconds,
    )

    if jobs == 0:
        logger.info("Scheduler not started (no jobs enabled)")
        return

    scheduler.start()
    logger.info("Scheduler started with %s job(s)", jobs)


__all__ = ["start_scheduler"]
