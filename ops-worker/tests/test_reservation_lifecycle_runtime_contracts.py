from reservation_lifecycle_runtime import (
    ReservationLifecycleRuntime,
    create_reservation_lifecycle_runtime,
)


def test_reservation_lifecycle_runtime_forwards_start_and_end_callbacks():
    calls = []

    def start_impl(payload, **kwargs):
        calls.append(("start", payload, kwargs))
        return {"action": "start"}, 200

    def end_impl(payload, **kwargs):
        calls.append(("end", payload, kwargs))
        return {"action": "end"}, 200

    providers = {
        "_handle_reservation_start_impl": start_impl,
        "_handle_reservation_end_impl": end_impl,
        "HOSTS": {"station": {"name": "station"}},
        "_get_mandatory_field": lambda payload, *keys: "value",
        "parse_bool": lambda value, default=True: bool(value),
        "_execute_reservation_power_phase": lambda *args: ("power", args),
        "perform_wake_step": lambda *args: ("wake", args),
        "perform_command_step": lambda *args: ("command", args),
        "normalize_args": lambda value, default=None: list(value or default or []),
    }
    runtime = create_reservation_lifecycle_runtime(providers)

    assert isinstance(runtime, ReservationLifecycleRuntime)
    assert runtime.handle_reservation_start({"id": "start"}) == ({"action": "start"}, 200)
    assert runtime.handle_reservation_end({"id": "end"}) == ({"action": "end"}, 200)
    assert [call[0] for call in calls] == ["start", "end"]
    assert calls[0][2]["find_host"]("station") == {"name": "station"}
    assert calls[1][2]["find_host"]("station") == {"name": "station"}


def test_reservation_lifecycle_runtime_resolves_mutable_host_and_step_callbacks():
    providers = {
        "_handle_reservation_start_impl": lambda payload, **kwargs: kwargs[
            "find_host"
        ]("station"),
        "HOSTS": {"station": "first"},
        "_get_mandatory_field": lambda payload, *keys: None,
        "parse_bool": bool,
        "_execute_reservation_power_phase": lambda *args: None,
        "perform_wake_step": lambda *args: None,
        "perform_command_step": lambda *args: None,
        "normalize_args": lambda value, default=None: [],
        "_handle_reservation_end_impl": lambda payload, **kwargs: None,
    }
    runtime = create_reservation_lifecycle_runtime(providers)

    assert runtime.handle_reservation_start({}) == "first"
    providers["HOSTS"] = {"station": "second"}
    assert runtime.handle_reservation_start({}) == "second"
