from datetime import datetime, timedelta, timezone

from lab_status_service import project_lab_status


NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)


def heartbeat(**overrides):
    value = {
        "timestamp": (NOW - timedelta(seconds=30)).isoformat(),
        "ready": True,
        "localMode": False,
        "localSession": False,
    }
    value.update(overrides)
    return value


def test_fresh_ready_heartbeat_is_positive():
    result = project_lab_status("7", heartbeat(), now=NOW, max_age_seconds=180)

    assert result["state"] == "ready"
    assert result["severity"] == "positive"
    assert result["ageSeconds"] == 30
    assert result["reason"] == "station_ready"


def test_fmu_only_issue_keeps_physical_lab_ready_but_marks_fmu_not_ready():
    result = project_lab_status(
        "7",
        heartbeat(
            ready=False,
            readiness={
                "physicalLab": {"ready": True},
                "fmu": {"ready": False},
            },
        ),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "ready"
    assert result["reason"] == "station_ready"
    assert result["capabilities"]["physicalLab"]["state"] == "ready"
    assert result["capabilities"]["fmu"]["state"] == "not_ready"
    assert result["capabilities"]["fmu"]["reason"] == "fmu_not_ready"


def test_local_session_is_busy_with_warning_severity():
    result = project_lab_status(
        7,
        heartbeat(localSession=True),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "busy"
    assert result["severity"] == "warning"
    assert result["reason"] == "local_session_active"


def test_local_mode_is_busy_with_critical_severity():
    result = project_lab_status(
        7,
        heartbeat(localMode=True),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "busy"
    assert result["severity"] == "critical"
    assert result["reason"] == "local_mode_enabled"


def test_stale_heartbeat_is_unknown_even_when_station_was_ready():
    result = project_lab_status(
        7,
        heartbeat(timestamp=(NOW - timedelta(seconds=181)).isoformat()),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "unknown"
    assert result["reason"] == "heartbeat_stale"
    assert result["ageSeconds"] == 181


def test_missing_mapping_is_unknown_without_exposing_host_details():
    result = project_lab_status(
        7,
        None,
        now=NOW,
        max_age_seconds=180,
        host_mapped=False,
    )

    assert result["state"] == "unknown"
    assert result["reason"] == "lab_not_mapped"
    assert set(result) == {
        "labId", "state", "reason", "source", "observedAt", "ageSeconds",
        "severity", "generatedAt",
    }


def test_guacamole_probe_is_used_when_station_heartbeat_is_not_fresh():
    result = project_lab_status(
        7,
        None,
        now=NOW,
        max_age_seconds=180,
        host_mapped=False,
        target_probe={
            "signal": "reachable",
            "reason": "target_reachable",
            "source": "guacamole_tcp_probe",
            "observedAt": (NOW - timedelta(seconds=8)).isoformat(),
        },
    )

    assert result["state"] == "reachable"
    assert result["severity"] == "positive"
    assert result["source"] == "guacamole_tcp_probe"
    assert result["reason"] == "target_reachable"
    assert result["ageSeconds"] == 8


def test_fresh_station_heartbeat_takes_precedence_over_guacamole_probe():
    result = project_lab_status(
        7,
        heartbeat(),
        now=NOW,
        max_age_seconds=180,
        target_probe={
            "signal": "unreachable",
            "reason": "target_unreachable",
            "source": "guacamole_tcp_probe",
            "observedAt": NOW.isoformat(),
        },
    )

    assert result["state"] == "ready"
    assert result["source"] == "lab_station_heartbeat"
