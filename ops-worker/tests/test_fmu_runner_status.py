from datetime import datetime, timezone

from fmu_runner_status import CachedFmuRunnerStatus


NOW = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def _probe(payload):
    calls = []
    clock = [100.0]

    class Response:
        def json(self):
            return payload

    probe = CachedFmuRunnerStatus(
        http_get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
        url="http://fmu-runner:8090/health",
        timeout_seconds=1.5,
        cache_seconds=15,
        now=lambda: NOW,
        monotonic=lambda: clock[0],
    )
    return probe, calls, clock


def test_local_runner_with_fmus_is_ready_and_cached():
    probe, calls, clock = _probe({
        "status": "UP",
        "backendMode": "local",
        "fmuCount": 7,
    })

    assert probe.get_status()["signal"] == "ready"
    clock[0] = 110.0
    assert probe.get_status()["reason"] == "fmu_ready"
    assert len(calls) == 1


def test_station_runner_health_is_available_as_fmu_status_fallback():
    probe, _calls, _clock = _probe({
        "status": "UP",
        "backendMode": "station",
        "fmuCount": 7,
    })

    assert probe.get_status()["signal"] == "ready"
    assert probe.get_status()["reason"] == "fmu_ready"


def test_degraded_local_runner_is_not_ready():
    probe, _calls, _clock = _probe({
        "status": "DEGRADED",
        "backendMode": "local",
        "fmuCount": 7,
    })

    assert probe.get_status()["signal"] == "not_ready"
    assert probe.get_status()["reason"] == "fmu_not_ready"
