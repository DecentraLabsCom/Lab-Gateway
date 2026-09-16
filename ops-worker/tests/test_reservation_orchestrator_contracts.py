from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

from reservation_orchestrator import ReservationOrchestrator
from reservation_orchestrator import SchedulerProtocol


class _Registry:
    pass


class _Response:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def _orchestrator(http_get=None, **env):
    values = {
        "OPS_RESERVATION_AUTOMATION": "false",
        "OPS_RESERVATION_SCAN_INTERVAL": "30",
        "OPS_RESERVATION_START_LEAD": "120",
        "OPS_RESERVATION_END_DELAY": "60",
        "OPS_RESERVATION_LOOKBACK": "21600",
        "OPS_RESERVATION_RETRY_COOLDOWN": "60",
        "OPS_RESERVATION_MAX_BATCH": "200",
        **env,
    }
    return ReservationOrchestrator(
        object(),
        _Registry(),
        parse_bool=lambda value, default=False: str(value).lower() in {"true", "1", "yes", "on"},
        get_env=lambda name, default=None: values.get(name, default),
        env_or_secret_file=lambda _name: values.get("RESERVATION_PROJECTION_TOKEN", ""),
        parse_reservation_datetime=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None,
        as_utc_datetime=lambda value: value if isinstance(value, datetime) else None,
        http_get=http_get or Mock(),
        sql_text=lambda value: value,
        bindparam=lambda *args, **kwargs: (args, kwargs),
        dispatch_start=Mock(),
        dispatch_end=Mock(),
        resolve_host_by_lab=lambda _lab_id: None,
        record_operation=Mock(),
        logger=Mock(),
        now=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
    )


def test_remote_candidates_preserve_auth_scope_window_and_filtering():
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    response = _Response(
        {
            "gatewayId": "lite.example",
            "reservations": [
                {
                    "transactionHash": "reservation-1",
                    "labId": "lab-1",
                    "startTime": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
                    "endTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "status": "confirmed",
                },
                {"transactionHash": "invalid", "labId": "", "status": "CONFIRMED"},
            ],
        }
    )
    http_get = Mock(return_value=response)
    orchestrator = _orchestrator(
        http_get=http_get,
        RESERVATION_PROJECTION_URL="https://full.example/projection",
        RESERVATION_PROJECTION_GATEWAY_ID="Lite.Example",
        RESERVATION_PROJECTION_TOKEN="projection-secret",
    )

    rows = orchestrator._fetch_remote_candidates(now)

    assert rows == [
        {
            "transaction_hash": "reservation-1",
            "lab_id": "lab-1",
            "start_time": now + timedelta(seconds=30),
            "end_time": now + timedelta(hours=1),
            "status": "CONFIRMED",
        }
    ]
    http_get.assert_called_once()
    assert http_get.call_args.kwargs["headers"] == {
        "X-Gateway-ID": "lite.example",
        "X-Reservation-Projection-Token": "projection-secret",
    }


def test_register_preserves_disabled_and_enabled_job_contract():
    class _Scheduler(SchedulerProtocol):
        def __init__(self):
            self.calls = []

        def add_job(self, *args: Any, **kwargs: Any) -> None:
            self.calls.append((args, kwargs))

    disabled_scheduler = _Scheduler()
    assert _orchestrator().register(disabled_scheduler) == 0
    assert disabled_scheduler.calls == []

    enabled_scheduler = _Scheduler()
    enabled = _orchestrator(OPS_RESERVATION_AUTOMATION="true")
    assert enabled.register(enabled_scheduler) == 1
    assert len(enabled_scheduler.calls) == 1
    assert enabled_scheduler.calls[0][1]["id"] == "reservation-orchestrator"
    assert enabled_scheduler.calls[0][1]["replace_existing"] is True


def test_dispatch_start_resolves_the_current_host_from_the_lab_id():
    resolver = Mock(return_value={"name": "station-current"})
    dispatch = Mock(return_value=({"success": True}, 200))
    orchestrator = _orchestrator()
    orchestrator.resolve_host_by_lab = resolver
    orchestrator.dispatch_start = dispatch

    orchestrator._dispatch_start({
        "transaction_hash": "reservation-1",
        "lab_id": "lab-1",
        "status": None,
    })

    resolver.assert_called_once_with("lab-1")
    dispatch.assert_called_once_with({
        "reservationId": "reservation-1",
        "host": "station-current",
        "labId": "lab-1",
    })
