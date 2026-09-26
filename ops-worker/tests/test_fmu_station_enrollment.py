from fmu_station_enrollment import (
    FmuStationConfig,
    FmuStationEnrollmentError,
    build_fmu_station_provision_script,
    build_fmu_station_release_script,
    enroll_fmu_station,
    public_station_status,
    release_fmu_station,
    resolve_station_host,
)


HOSTS = [
    {"name": "lab-ws-01", "address": "192.168.1.50"},
    {"name": "lab-ws-02", "address": "192.168.1.51"},
]
TOKEN = "fmu_" + "a" * 64


def test_station_resolution_is_single_and_uses_configured_host_first():
    station = resolve_station_host(
        HOSTS,
        configured_host="lab-ws-01",
        base_url="http://192.168.1.51:8091",
    )

    assert station == HOSTS[0]


def test_public_status_does_not_expose_internal_token():
    payload = public_station_status(
        FmuStationConfig(
            backend_mode="station",
            base_url="http://192.168.1.50:8091",
            configured_host="",
            internal_token=TOKEN,
        ),
        HOSTS,
        runner_health={
            "status": "UP",
            "checks": {
                "stationHealth": True,
                "stationAuthentication": True,
            },
        },
    )

    assert payload["configured"] is True
    assert payload["singleStationPerGateway"] is True
    assert payload["stationHost"] == "lab-ws-01"
    assert payload["runner"]["stationAuthenticated"] is True
    assert payload["linked"] is True
    assert payload["linkedHost"] == "lab-ws-01"
    assert payload["linkStatus"] == "linked"
    assert TOKEN not in str(payload)


def test_public_status_marks_link_state_unknown_when_runner_health_is_unavailable():
    payload = public_station_status(
        FmuStationConfig(
            backend_mode="station",
            base_url="http://192.168.1.50:8091",
            configured_host="",
            internal_token=TOKEN,
        ),
        HOSTS,
        runner_health={"status": "DOWN"},
    )

    assert payload["linkStatus"] == "unknown"


def test_provision_script_does_not_embed_plaintext_token_and_restarts_background_task():
    script = build_fmu_station_provision_script(TOKEN)

    assert TOKEN not in script
    assert "SetEnvironmentVariable('FMU_INTERNAL_TOKEN', $token, 'Machine')" in script
    assert "Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName" in script
    assert "Stop-ScheduledTask" in script
    assert "Start-ScheduledTask" in script


def test_release_script_clears_machine_token_and_restarts_background_task():
    script = build_fmu_station_release_script()

    assert "FMU_INTERNAL_TOKEN" in script
    assert "SetEnvironmentVariable('FMU_INTERNAL_TOKEN', $null, 'Machine')" in script
    assert "Stop-ScheduledTask" in script
    assert "Start-ScheduledTask" in script


def test_release_uses_only_the_configured_station_host():
    calls = []
    result = release_fmu_station(
        {"host": "lab-ws-01"},
        config=FmuStationConfig(
            backend_mode="station",
            base_url="http://192.168.1.50:8091",
            configured_host="",
            internal_token=TOKEN,
        ),
        hosts=HOSTS,
        run_remote_powershell=lambda **kwargs: calls.append(kwargs),
    )

    assert result == {
        "released": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "restartRequested": True,
    }
    assert calls[0]["host"] == HOSTS[0]
    assert "$null" in calls[0]["script"]


def test_enroll_uses_only_the_configured_station_host():
    calls = []
    result = enroll_fmu_station(
        {"host": "lab-ws-01"},
        config=FmuStationConfig(
            backend_mode="station",
            base_url="http://192.168.1.50:8091",
            configured_host="",
            internal_token=TOKEN,
        ),
        hosts=HOSTS,
        run_remote_powershell=lambda **kwargs: calls.append(kwargs),
    )

    assert result == {
        "enrolled": True,
        "host": "lab-ws-01",
        "address": "192.168.1.50",
        "restartRequested": True,
    }
    assert calls[0]["host"] == HOSTS[0]
    assert TOKEN not in calls[0]["script"]


def test_enroll_rejects_a_second_host_on_the_same_gateway():
    calls = []

    try:
        enroll_fmu_station(
            {"host": "lab-ws-02"},
            config=FmuStationConfig(
                backend_mode="station",
                base_url="http://192.168.1.50:8091",
                configured_host="",
                internal_token=TOKEN,
            ),
            hosts=HOSTS,
            run_remote_powershell=lambda **kwargs: calls.append(kwargs),
        )
    except FmuStationEnrollmentError as exc:
        assert exc.code == "FMU_STATION_HOST_MISMATCH"
        assert exc.status_code == 409
    else:
        raise AssertionError("a Gateway must not enroll a second FMU Station")

    assert calls == []
