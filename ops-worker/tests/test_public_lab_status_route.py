from datetime import datetime, timezone

import pytest

from public_lab_status_route import build_public_lab_status_response, parse_lab_ids


def test_parse_lab_ids_accepts_repeated_and_comma_separated_values():
    assert parse_lab_ids(["1, 2", "2", "003"]) == ["1", "2", "3"]


def test_parse_lab_ids_rejects_empty_and_invalid_values():
    with pytest.raises(ValueError):
        parse_lab_ids([])
    with pytest.raises(ValueError):
        parse_lab_ids(["1,abc"])


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Engine:
    def __init__(self):
        self.connection = Connection()

    def connect(self):
        return self.connection


def test_build_response_reads_only_mapped_hosts_and_closes_connection():
    engine = Engine()
    heartbeat = {
        "timestamp": "2026-09-23T10:00:00+00:00",
        "ready": True,
        "localMode": False,
        "localSession": False,
    }
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)
    calls = []

    result = build_public_lab_status_response(
        ["7", "8"],
        engine=engine,
        resolve_lab_associations=lambda: [{"labId": "7", "hostName": "private-host"}],
        resolve_lab_status_targets=lambda: [{
            "labId": "7",
            "hostName": "private-host",
            "hostname": "private-host",
            "protocol": "rdp",
            "port": "3389",
        }],
        fetch_latest_heartbeat=lambda connection, host_name: calls.append(host_name) or heartbeat,
        probe_lab_targets=lambda targets: {},
        now=now,
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "ready"
    assert result["statuses"][1]["state"] == "unknown"
    assert calls == ["private-host"]
    assert engine.connection.closed is True
    assert "private-host" not in str(result)


def test_build_response_exposes_access_wake_and_availability_dimensions():
    engine = Engine()
    heartbeat = {
        "timestamp": "2026-09-23T09:57:00+00:00",
        "ready": False,
        "localMode": False,
        "localSession": False,
    }
    wake_operations = []

    result = build_public_lab_status_response(
        ["7"],
        engine=engine,
        resolve_lab_associations=lambda: [{
            "labId": "7",
            "hostName": "private-host",
            "wakeConfigured": True,
        }],
        resolve_lab_status_targets=lambda: [],
        fetch_latest_heartbeat=lambda *_args: heartbeat,
        fetch_latest_wake_operations=lambda _connection, lab_ids: (
            wake_operations.append(list(lab_ids)) or {
                "7": {
                    "success": True,
                    "status": "completed",
                    "created_at": datetime(2026, 9, 23, 9, 58, tzinfo=timezone.utc),
                },
            }
        ),
        probe_lab_targets=lambda _targets: {},
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["access"] == "unknown"
    assert status["wake"]["state"] == "verified"
    assert status["availability"] == "on_demand"
    assert wake_operations == [["7"]]


def test_fresh_station_wake_diagnosis_can_reject_host_configuration():
    result = build_public_lab_status_response(
        ["7"],
        engine=Engine(),
        resolve_lab_associations=lambda: [{
            "labId": "7",
            "hostName": "private-host",
            "wakeConfigured": True,
        }],
        resolve_lab_status_targets=lambda: [],
        fetch_latest_heartbeat=lambda *_args: {
            "timestamp": "2026-09-23T10:00:00+00:00",
            "ready": True,
            "readiness": {"wake": {"ready": False, "issues": ["NIC not wake-armed"]}},
        },
        fetch_latest_wake_operations=lambda *_args: {},
        probe_lab_targets=lambda _targets: {},
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["state"] == "ready"
    assert status["wake"]["state"] == "failed"


def test_build_response_publishes_capability_statuses_without_raw_diagnostics():
    engine = Engine()
    heartbeat = {
        "timestamp": "2026-09-23T10:00:00+00:00",
        "ready": False,
        "localMode": False,
        "localSession": False,
        "readiness": {
            "physicalLab": {"ready": True, "issues": []},
            "fmu": {"ready": False, "issues": ["secret must not be public"]},
        },
    }
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)

    result = build_public_lab_status_response(
        ["7"],
        engine=engine,
        resolve_lab_associations=lambda: [{"labId": "7", "hostName": "private-host"}],
        resolve_lab_status_targets=lambda: [],
        fetch_latest_heartbeat=lambda *_args: heartbeat,
        probe_lab_targets=lambda targets: {},
        now=now,
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["state"] == "ready"
    assert status["capabilities"]["physicalLab"]["state"] == "ready"
    assert status["capabilities"]["fmu"]["state"] == "not_ready"
    assert "secret must not be public" not in str(result)


def test_build_response_uses_capability_readiness_from_persisted_raw_heartbeat():
    engine = Engine()
    persisted_heartbeat = {
        "timestamp": "2026-09-23T10:00:00+00:00",
        "ready": False,
        "localMode": False,
        "localSession": False,
        "raw": {
            "timestamp": "2026-09-23T10:00:00+00:00",
            "summary": {"ready": False},
            "readiness": {
                "physicalLab": {"ready": True, "issues": []},
                "fmu": {"ready": False, "issues": ["FMU executor is not running"]},
            },
            "status": {"localModeEnabled": False, "localSessionActive": False},
        },
    }
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)

    result = build_public_lab_status_response(
        ["7"],
        engine=engine,
        resolve_lab_associations=lambda: [{"labId": "7", "hostName": "private-host"}],
        resolve_lab_status_targets=lambda: [],
        fetch_latest_heartbeat=lambda *_args: persisted_heartbeat,
        probe_lab_targets=lambda targets: {},
        now=now,
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["state"] == "ready"
    assert status["reason"] == "station_ready"
    assert status["capabilities"]["physicalLab"]["state"] == "ready"
    assert status["capabilities"]["fmu"]["state"] == "not_ready"


def test_build_response_uses_guacamole_probe_for_lab_without_station_mapping():
    engine = Engine()
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)
    probed = []

    result = build_public_lab_status_response(
        ["8"],
        engine=engine,
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [{
            "labId": "8",
            "connectionId": "9",
            "hostname": "linux-only",
            "protocol": "ssh",
            "port": "22",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("a lab without a Station mapping must not read heartbeats")
        ),
        probe_lab_targets=lambda targets: probed.append(targets) or {
            "8": {
                "signal": "reachable",
                "reason": "target_reachable",
                "source": "guacamole_tcp_probe",
                "observedAt": "2026-09-23T10:00:20+00:00",
            }
        },
        now=now,
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "reachable"
    assert result["statuses"][0]["source"] == "guacamole_tcp_probe"
    assert probed[0][0]["hostname"] == "linux-only"
    assert "linux-only" not in str(result)


def test_build_response_uses_local_fmu_runner_for_fmu_without_station_mapping():
    engine = Engine()
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)
    calls = []

    result = build_public_lab_status_response(
        ["9"],
        engine=engine,
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [],
        resolve_lab_resources=lambda: [{
            "labId": "9",
            "resourceType": "fmu",
            "executionBackend": "local",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("an FMU must not read a Station heartbeat")
        ),
        probe_lab_targets=lambda _targets: (_ for _ in ()).throw(
            AssertionError("an FMU must not probe Guacamole")
        ),
        fetch_fmu_runner_status=lambda _lab_id: calls.append("health") or {
            "signal": "ready",
            "reason": "fmu_ready",
            "source": "fmu_runner_health",
            "observedAt": "2026-09-23T10:00:29Z",
        },
        now=now,
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["state"] == "ready"
    assert status["source"] == "fmu_runner_health"
    assert status["capabilities"]["fmu"]["state"] == "ready"
    assert calls == ["health"]


def test_build_response_does_not_load_station_dependencies_for_local_fmu():
    calls = []

    result = build_public_lab_status_response(
        ["12"],
        engine=Engine(),
        resolve_lab_associations=lambda: calls.append("associations") or [],
        resolve_lab_status_targets=lambda: calls.append("targets") or [],
        resolve_lab_resources=lambda: calls.append("resources") or [{
            "labId": "12",
            "resourceType": "fmu",
            "executionBackend": "local",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("a local FMU must not load a Station heartbeat")
        ),
        probe_lab_targets=lambda _targets: (_ for _ in ()).throw(
            AssertionError("a local FMU must not probe Guacamole")
        ),
        fetch_fmu_runner_status=lambda _lab_id: calls.append("health") or {
            "signal": "ready",
            "reason": "fmu_ready",
            "source": "fmu_runner_health",
            "observedAt": "2026-09-23T10:00:29Z",
        },
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "ready"
    assert calls == ["resources", "health"]


def test_build_response_keeps_local_fmu_unknown_when_runner_health_is_unavailable():
    result = build_public_lab_status_response(
        ["9"],
        engine=Engine(),
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [],
        resolve_lab_resources=lambda: [{
            "labId": "9",
            "resourceType": "fmu",
            "executionBackend": "local",
        }],
        fetch_latest_heartbeat=lambda *_args: None,
        probe_lab_targets=lambda _targets: {},
        fetch_fmu_runner_status=lambda _lab_id: {
            "signal": "unknown",
            "reason": "fmu_runner_unavailable",
            "source": "fmu_runner_health",
            "observedAt": "2026-09-23T10:00:29Z",
        },
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "unknown"
    assert result["statuses"][0]["reason"] == "fmu_runner_unavailable"


def test_build_response_uses_fmu_runner_for_station_fmu_without_guacamole_or_heartbeat():
    calls = []

    result = build_public_lab_status_response(
        ["10"],
        engine=Engine(),
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [],
        resolve_lab_resources=lambda: [{
            "labId": "10",
            "resourceType": "fmu",
            "executionBackend": "station",
            "stationHostName": "station-01",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("a Station FMU must not read a physical-lab heartbeat")
        ),
        probe_lab_targets=lambda _targets: (_ for _ in ()).throw(
            AssertionError("a Station FMU must not probe Guacamole")
        ),
        fetch_fmu_runner_status=lambda lab_id: calls.append(lab_id) or {
            "signal": "ready",
            "reason": "fmu_ready",
            "source": "fmu_runner_health",
            "observedAt": "2026-09-23T10:00:29Z",
            "capacity": {"state": "available", "active": 0, "maximum": 1, "available": 1},
        },
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    status = result["statuses"][0]
    assert status["state"] == "ready"
    assert status["reason"] == "fmu_ready"
    assert status["source"] == "fmu_runner_health"
    assert status["resourceType"] == "fmu"
    assert status["capabilities"]["fmu"]["state"] == "ready"
    assert "wake" not in status
    assert calls == ["10"]


def test_build_response_falls_back_to_runner_for_station_fmu_without_station_host():
    calls = []

    result = build_public_lab_status_response(
        ["11"],
        engine=Engine(),
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [],
        resolve_lab_resources=lambda: [{
            "labId": "11",
            "resourceType": "fmu",
            "executionBackend": "station",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("an unmapped Station FMU must not read an arbitrary heartbeat")
        ),
        probe_lab_targets=lambda _targets: {},
        fetch_fmu_runner_status=lambda _lab_id: calls.append("health") or {
            "signal": "ready",
            "reason": "fmu_ready",
            "source": "fmu_runner_health",
            "observedAt": "2026-09-23T10:00:29Z",
        },
        now=lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "ready"
    assert result["statuses"][0]["source"] == "fmu_runner_health"
    assert calls == ["health"]
