import json

import pytest

from station_action_policy import StationActionPolicyError, validate_operator_station_action


def _run_with_status(status):
    def run_station_command(_host, command, _args):
        assert command == "status-json"
        return {"exitCode": 0, "stdout": json.dumps(status)}

    return run_station_command


def test_dedicated_prepare_blocks_any_local_console_account_including_labuser():
    status = {
        "profile": "dedicated",
        "localModeEnabled": False,
        "localSessionActive": True,
        "sessions": {
            "queryOk": True,
            "localSessionActive": True,
            "labUserRemoteActive": False,
            "active": [{"kind": "labuser-local", "active": True}],
        },
    }

    with pytest.raises(StationActionPolicyError) as error:
        validate_operator_station_action(
            {"name": "station-1"},
            "prepare-session",
            [],
            run_station_command=_run_with_status(status),
        )

    assert error.value.code == "STATION_LOCAL_SESSION_ACTIVE"


def test_dedicated_prepare_does_not_treat_another_users_rdp_session_as_local():
    status = {
        "profile": "dedicated",
        "localModeEnabled": False,
        "localSessionActive": False,
        "sessions": {
            "queryOk": True,
            "localSessionActive": False,
            "remoteSessionActive": True,
            "labUserRemoteActive": False,
            "active": [{"kind": "remote-user", "active": True}],
        },
    }

    validate_operator_station_action(
        {"name": "station-1"},
        "prepare-session",
        [],
        run_station_command=_run_with_status(status),
    )


def test_dedicated_prepare_fails_closed_when_legacy_and_nested_local_state_disagree():
    status = {
        "profile": "dedicated",
        "localModeEnabled": False,
        "localSessionActive": False,
        "sessions": {"queryOk": True, "localSessionActive": True},
    }

    with pytest.raises(StationActionPolicyError) as error:
        validate_operator_station_action(
            {"name": "station-1"},
            "prepare-session",
            [],
            run_station_command=_run_with_status(status),
        )

    assert error.value.code == "STATION_SESSION_STATE_UNKNOWN"


def test_prepare_refuses_active_remote_labuser_and_explains_workspace_cleanup():
    status = {
        "profile": "hybrid",
        "localModeEnabled": False,
        "sessions": {
            "queryOk": True,
            "localSessionActive": False,
            "labUserRemoteActive": True,
        },
    }

    with pytest.raises(StationActionPolicyError) as error:
        validate_operator_station_action(
            {"name": "station-1"},
            "prepare-session",
            [],
            run_station_command=_run_with_status(status),
        )

    assert error.value.code == "STATION_REMOTE_SESSION_ACTIVE"
    assert "Downloads" in str(error.value)
    assert "no cleanup ran" in str(error.value)


def test_prepare_fails_closed_when_remote_labuser_state_is_missing():
    status = {
        "profile": "dedicated",
        "localModeEnabled": False,
        "sessions": {"queryOk": True, "localSessionActive": False},
    }

    with pytest.raises(StationActionPolicyError) as error:
        validate_operator_station_action(
            {"name": "station-1"},
            "prepare-session",
            [],
            run_station_command=_run_with_status(status),
        )

    assert error.value.code == "STATION_SESSION_STATE_UNKNOWN"
