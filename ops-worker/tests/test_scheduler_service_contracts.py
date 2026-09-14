from datetime import datetime, timezone

from scheduler_service import start_scheduler


class _Scheduler:
    def __init__(self):
        self.jobs = []
        self.started = False

    def add_job(self, function, trigger, **kwargs):
        self.jobs.append((function, trigger, kwargs))

    def start(self):
        self.started = True


class _Logger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append((message, args))


def test_start_scheduler_contract_preserves_job_order_and_intervals():
    scheduler = _Scheduler()
    logger = _Logger()
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    calls = []

    start_scheduler(
        scheduler_factory=lambda: scheduler,
        poll_enabled=True,
        poll_interval_seconds=60,
        poll_all_hosts=lambda: calls.append("poll"),
        register_reservation_jobs=lambda received: calls.append(("reservation", received)) or 2,
        cleanup_enabled=True,
        cleanup_interval_seconds=900,
        cleanup_expired_users=lambda: calls.append("cleanup"),
        observation_enabled=True,
        observation_interval_seconds=5,
        deliver_observations=lambda: calls.append("observations"),
        revocation_interval_seconds=10,
        process_revocations=lambda: calls.append("revocations"),
        now=lambda: now,
        logger=logger,
    )

    assert [job[2]["id"] for job in scheduler.jobs] == [
        "heartbeat-poller",
        "guacamole-temp-user-cleanup",
        "session-observation-outbox",
        "guacamole-token-revocation",
    ]
    assert [job[2]["seconds"] for job in scheduler.jobs] == [60, 900, 5, 10]
    assert all(job[1] == "interval" for job in scheduler.jobs)
    assert all(job[2]["next_run_time"] == now for job in scheduler.jobs)
    assert all(job[2]["replace_existing"] is True for job in scheduler.jobs)
    assert calls == [("reservation", scheduler)]
    assert scheduler.started is True


def test_start_scheduler_contract_always_registers_revocations_and_logs_start():
    scheduler = _Scheduler()
    logger = _Logger()

    start_scheduler(
        scheduler_factory=lambda: scheduler,
        poll_enabled=False,
        poll_interval_seconds=60,
        poll_all_hosts=lambda: None,
        register_reservation_jobs=lambda _scheduler: 0,
        cleanup_enabled=False,
        cleanup_interval_seconds=900,
        cleanup_expired_users=lambda: None,
        observation_enabled=False,
        observation_interval_seconds=5,
        deliver_observations=lambda: None,
        revocation_interval_seconds=10,
        process_revocations=lambda: None,
        now=lambda: datetime.now(timezone.utc),
        logger=logger,
    )

    assert len(scheduler.jobs) == 1
    assert scheduler.jobs[0][2]["id"] == "guacamole-token-revocation"
    assert scheduler.started is True
    assert any("Scheduler started with %s job(s)" in message for message, _ in logger.messages)
