from types import SimpleNamespace

from scheduler_runtime import SchedulerRuntime, create_scheduler_runtime


def test_scheduler_runtime_forwards_environment_and_job_callbacks():
    calls = []
    providers = {
        "_start_scheduler_impl": lambda **kwargs: calls.append(kwargs),
        "BackgroundScheduler": "scheduler-factory",
        "os": SimpleNamespace(
            getenv=lambda name, default=None: {
                "OPS_POLL_ENABLED": "true",
                "OPS_POLL_INTERVAL": "45",
            }.get(name, default)
        ),
        "poll_all_hosts": "poll",
        "RESERVATION_AUTOMATOR": SimpleNamespace(register="register"),
        "GUACAMOLE_TEMP_USER_CLEANUP_ENABLED": True,
        "GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS": 900,
        "cleanup_expired_guacamole_temp_users": "cleanup",
        "SESSION_OBSERVATION_OUTBOX_ENABLED": True,
        "SESSION_OBSERVATION_OUTBOX_INTERVAL_SECONDS": 5,
        "deliver_session_observation_outbox": "observations",
        "GUAC_TOKEN_REVOCATION_INTERVAL_SECONDS": 10,
        "process_guacamole_token_revocations": "revocations",
        "datetime": SimpleNamespace(now="now"),
        "timezone": SimpleNamespace(utc="UTC"),
        "logging": "logger",
    }
    runtime = create_scheduler_runtime(providers)

    assert isinstance(runtime, SchedulerRuntime)
    assert runtime.start_scheduler() is None
    received = calls[0]
    assert received["poll_enabled"] is True
    assert received["poll_interval_seconds"] == 45
    assert received["poll_all_hosts"] == "poll"
    assert received["register_reservation_jobs"] == "register"
    assert received["cleanup_enabled"] is True
    assert received["cleanup_interval_seconds"] == 900
    assert received["cleanup_expired_users"] == "cleanup"
    assert received["observation_enabled"] is True
    assert received["observation_interval_seconds"] == 5
    assert received["deliver_observations"] == "observations"
    assert received["revocation_interval_seconds"] == 10
    assert received["process_revocations"] == "revocations"
    assert received["logger"] == "logger"
    assert callable(received["scheduler_factory"])
    assert callable(received["now"])
