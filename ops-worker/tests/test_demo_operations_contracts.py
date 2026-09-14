from unittest.mock import Mock

from demo_operations import handle_demo_event, handle_demo_start


def _context():
    return {"demo_id": "demo:jti-1", "lab_id": "42", "host": {"name": "lab-ws-01"}}


def test_demo_start_clamps_guard_grace_and_delegates_to_reservation():
    reservation_start = Mock(return_value=({"success": True, "steps": [{"action": "prepare"}]}, 200))
    record_event = Mock()

    response, status = handle_demo_start(
        {"demoId": "demo:jti-1", "labId": "42", "wake": False, "guardGrace": 999},
        get_context=lambda _payload: (_context(), None),
        operation_completed=lambda *_args: False,
        parse_bool=lambda value, default: default if value is None else bool(value),
        host_is_ready=lambda _host: True,
        reservation_start=reservation_start,
        reservation_end=Mock(),
        record_event=record_event,
    )

    assert status == 200
    assert response["success"] is True
    reservation_payload = reservation_start.call_args.args[0]
    assert reservation_payload["guardGrace"] == 600
    assert reservation_payload["wake"] is False
    assert record_event.call_args.args[:3] == (_context(), "start", True)


def test_demo_event_requires_completed_physical_start():
    record_event = Mock()

    response, status = handle_demo_event(
        {"demoId": "demo:jti-1", "labId": "42", "event": "connected"},
        get_context=lambda _payload: (_context(), None),
        operation_completed=lambda _demo_id, action: action == "demo_cleanup",
        record_event=record_event,
        event_actions={"connected": "demo_connection"},
    )

    assert status == 409
    assert response == {
        "success": False,
        "error": "demo physical preparation has not completed",
    }
    record_event.assert_not_called()
