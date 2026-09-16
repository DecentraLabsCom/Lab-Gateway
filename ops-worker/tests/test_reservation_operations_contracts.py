from unittest.mock import Mock

from reservation_operations import handle_reservation_end, handle_reservation_start


def _dependencies():
    host = {"name": "lab-ws-01"}
    return {
        "find_host": lambda name: host if name == "lab-ws-01" else None,
        "resolve_host_by_lab": lambda lab_id: host if lab_id == "42" else None,
        "get_mandatory_field": lambda payload, *keys: next(
            (str(payload[key]).strip() for key in keys if payload.get(key) not in (None, "")),
            None,
        ),
        "parse_bool": lambda value, default: default if value is None else bool(value),
        "execute_power_phase": Mock(return_value={"success": True, "steps": []}),
        "perform_wake_step": Mock(return_value=(True, {"action": "wake", "success": True})),
        "perform_command_step": Mock(
            return_value=(True, {"action": "prepare", "success": True})
        ),
        "normalize_args": lambda value, default=None: list(value) if value is not None else list(default or []),
    }


def test_start_preserves_phase_order_and_defaults():
    deps = _dependencies()

    response, status = handle_reservation_start(
        {"reservationId": "r-1", "host": "lab-ws-01", "labId": "42"},
        **deps,
    )

    assert status == 200
    assert response["success"] is True
    assert [step["action"] for step in response["steps"]] == ["wake", "prepare"]
    assert deps["execute_power_phase"].call_args_list[0].args[3] == "pre_start"
    assert deps["execute_power_phase"].call_args_list[1].args[3] == "post_start"
    deps["perform_command_step"].assert_called_once_with(
        {"name": "lab-ws-01"},
        "r-1",
        "42",
        "prepare",
        "prepare-session",
        ["--guard-grace=90"],
    )


def test_start_uses_the_resolved_host_when_the_request_host_is_stale_or_missing():
    deps = _dependencies()

    response, status = handle_reservation_start(
        {"reservationId": "r-1", "labId": "42", "host": "old-station"},
        **deps,
    )

    assert status == 200
    assert response["host"] == "lab-ws-01"
    assert deps["perform_wake_step"].call_args.args[0] == {"name": "lab-ws-01"}


def test_end_rejects_missing_host_without_invoking_physical_callbacks():
    deps = _dependencies()

    response, status = handle_reservation_end(
        {"reservationId": "r-1"},
        **{key: value for key, value in deps.items() if key != "perform_wake_step"},
    )

    assert status == 400
    assert response == {"error": "reservationId and either host or labId are required"}
    deps["execute_power_phase"].assert_not_called()
    deps["perform_command_step"].assert_not_called()
