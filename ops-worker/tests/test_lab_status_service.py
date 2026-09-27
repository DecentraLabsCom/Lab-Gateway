from datetime import datetime, timedelta, timezone

from lab_status_service import project_fmu_runner_status, project_lab_status


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
    assert result["access"] == "ready"
    assert result["wake"]["state"] == "unknown"
    assert result["availability"] == "now"


def test_recent_successful_wake_makes_stale_access_available_on_demand():
    result = project_lab_status(
        "7",
        heartbeat(timestamp=(NOW - timedelta(seconds=181)).isoformat()),
        now=NOW,
        max_age_seconds=180,
        wake_status={
            "configured": True,
            "operation": {
                "success": True,
                "status": "completed",
                "created_at": NOW - timedelta(minutes=5),
            },
        },
    )

    assert result["state"] == "unknown"
    assert result["access"] == "unknown"
    assert result["wake"]["state"] == "verified"
    assert result["availability"] == "on_demand"


def test_configured_wake_without_recent_verification_is_recoverable():
    result = project_lab_status(
        "7",
        None,
        now=NOW,
        max_age_seconds=180,
        wake_status={"configured": True},
    )

    assert result["access"] == "unknown"
    assert result["wake"]["state"] == "configured"
    assert result["availability"] == "recoverable"


def test_old_successful_wake_does_not_remain_verified_forever():
    result = project_lab_status(
        "7",
        None,
        now=NOW,
        max_age_seconds=180,
        wake_status={
            "configured": True,
            "operation": {
                "success": True,
                "status": "completed",
                "created_at": NOW - timedelta(days=8),
            },
        },
    )

    assert result["wake"]["state"] == "configured"
    assert result["availability"] == "recoverable"


def test_successful_wake_evidence_remains_verified_for_one_week():
    result = project_lab_status(
        "7",
        None,
        now=NOW,
        max_age_seconds=180,
        wake_status={
            "configured": True,
            "operation": {
                "success": True,
                "status": "completed",
                "created_at": NOW - timedelta(days=6, hours=23),
            },
        },
    )

    assert result["wake"]["state"] == "verified"
    assert result["availability"] == "on_demand"


def test_successful_wake_evidence_expires_after_one_week():
    result = project_lab_status(
        "7",
        None,
        now=NOW,
        max_age_seconds=180,
        wake_status={
            "configured": True,
            "operation": {
                "success": True,
                "status": "completed",
                "created_at": NOW - timedelta(days=7, seconds=1),
            },
        },
    )

    assert result["wake"]["state"] == "configured"
    assert result["availability"] == "recoverable"


def test_recent_failed_wake_is_unavailable_but_does_not_hide_access_dimensions():
    result = project_lab_status(
        "7",
        heartbeat(timestamp=(NOW - timedelta(seconds=181)).isoformat()),
        now=NOW,
        max_age_seconds=180,
        wake_status={
            "configured": True,
            "operation": {
                "success": False,
                "status": "failed",
                "created_at": NOW - timedelta(minutes=5),
            },
        },
    )

    assert result["wake"]["state"] == "failed"
    assert result["availability"] == "unavailable"


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


def test_fmu_runner_capacity_is_busy_without_inheriting_physical_station_state():
    result = project_fmu_runner_status(
        "7",
        {
            "signal": "busy",
            "reason": "fmu_capacity_exhausted",
            "source": "fmu_runner_health",
            "observedAt": (NOW - timedelta(seconds=4)).isoformat(),
            "capacity": {
                "state": "busy",
                "active": 2,
                "maximum": 2,
                "available": 0,
            },
        },
        now=NOW,
    )

    assert result["resourceType"] == "fmu"
    assert result["state"] == "busy"
    assert result["severity"] == "warning"
    assert result["availability"] == "unavailable"
    assert result["capacity"]["available"] == 0
    assert "wake" not in result
    assert result["capabilities"]["fmu"]["state"] == "busy"


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


def test_lab_user_session_is_busy_with_warning_severity():
    result = project_lab_status(
        7,
        heartbeat(
            sessions={
                "active": True,
                "kind": "labuser-remote",
                "labUserActive": True,
                "labUserRemoteActive": True,
                "remoteSessionActive": True,
            },
        ),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "busy"
    assert result["severity"] == "warning"
    assert result["reason"] == "lab_user_session_active"


def test_remote_session_without_lab_user_is_also_busy():
    result = project_lab_status(
        7,
        heartbeat(
            sessions={
                "active": True,
                "kind": "remote-user",
                "labUserActive": False,
                "labUserRemoteActive": False,
                "remoteSessionActive": True,
            },
        ),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "busy"
    assert result["severity"] == "warning"
    assert result["reason"] == "remote_session_active"


def test_nested_lab_user_session_from_persisted_station_status_is_busy():
    result = project_lab_status(
        7,
        {
            **heartbeat(),
            "raw": {
                "status": {
                    "localModeEnabled": False,
                    "localSessionActive": False,
                    "sessions": {
                        "active": True,
                        "kind": "labuser-local",
                        "labUserActive": True,
                        "labUserRemoteActive": False,
                        "remoteSessionActive": False,
                    },
                },
            },
        },
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "busy"
    assert result["severity"] == "warning"
    assert result["reason"] == "lab_user_session_active"


def test_unavailable_session_query_is_not_projected_as_ready():
    result = project_lab_status(
        7,
        heartbeat(
            sessions={
                "active": False,
                "queryOk": False,
            },
        ),
        now=NOW,
        max_age_seconds=180,
    )

    assert result["state"] == "unknown"
    assert result["reason"] == "session_status_unavailable"


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
        "severity", "generatedAt", "access", "wake", "availability",
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
