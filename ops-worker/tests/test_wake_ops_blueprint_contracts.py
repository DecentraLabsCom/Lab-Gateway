from datetime import datetime, timezone

from flask import Flask

from app_hooks import internal_error_response, register_app_hooks
from wake_ops_blueprint import create_wake_ops_blueprint


def _app(calls, *, get_schedule=None):
    app = Flask("wake-ops-blueprint-contract")
    app.register_blueprint(
        create_wake_ops_blueprint(
            find_host=lambda host: {"name": host},
            get_schedule=get_schedule or (lambda host: {
                "enabled": True,
                "dayOfWeek": 6,
                "hour": 8,
                "minute": 0,
                "timezone": "Europe/Madrid",
                "lastScheduledAt": None,
                "lastStartedAt": None,
                "lastFinishedAt": None,
                "lastStatus": None,
                "lastMessage": None,
                "lastInitialPowerState": None,
            }),
            save_schedule=lambda host, payload: calls.append(("save", host, payload))
            or {
                "enabled": payload.get("enabled", True),
                "dayOfWeek": payload.get("dayOfWeek", 6),
                "hour": payload.get("hour", 8),
                "minute": payload.get("minute", 0),
                "timezone": payload.get("timezone", "Europe/Madrid"),
            },
            get_latest_wake=lambda _host: {
                "success": True,
                "status": "completed",
                "createdAt": datetime(2026, 9, 27, 6, tzinfo=timezone.utc),
                "message": "Host reachable",
            },
            manual_wake=lambda host: calls.append(("wake", host))
            or {"host": host, "success": True, "status": "completed"},
            now=lambda: datetime(2026, 9, 27, 6, 5, tzinfo=timezone.utc),
        )
    )
    register_app_hooks(
        app,
        internal_error_response=lambda context, exc: internal_error_response(
            context,
            exc,
            request_id=lambda: "test-request",
            sanitize_log_value=str,
            log_exception=lambda *_args: None,
        ),
        internal_auth_token=lambda: "",
        internal_auth_header=lambda: "X-Ops-Token",
        requires_internal_auth=lambda _path: False,
    )
    return app


def test_wake_ops_get_exposes_schedule_and_seven_day_evidence_window():
    response = _app([]).test_client().get("/api/wake-ops/lab-ws-01")

    assert response.status_code == 200
    body = response.get_json()
    assert body["schedule"]["timezone"] == "Europe/Madrid"
    assert body["evidence"]["state"] == "verified"
    assert body["evidence"]["validForSeconds"] == 7 * 24 * 60 * 60


def test_wake_ops_update_and_manual_wake_are_separate_actions():
    calls = []
    client = _app(calls).test_client()

    update = client.put(
        "/api/wake-ops/lab-ws-01",
        json={"enabled": False, "dayOfWeek": 2, "hour": 9, "minute": 30},
    )
    wake = client.post("/api/wake-ops/lab-ws-01/wake")

    assert update.status_code == 200
    assert wake.status_code == 200
    assert calls == [
        ("save", "lab-ws-01", {"enabled": False, "dayOfWeek": 2, "hour": 9, "minute": 30}),
        ("wake", "lab-ws-01"),
    ]


def test_wake_ops_error_response_does_not_expose_exception_details():
    def fail(_host):
        raise RuntimeError("private database stack details")

    response = _app([], get_schedule=fail).test_client().get("/api/wake-ops/lab-ws-01")

    assert response.status_code == 500
    assert response.get_json() == {
        "error": "Internal server error",
        "code": "INTERNAL_ERROR",
        "requestId": "test-request",
    }
    assert b"private database stack details" not in response.data
