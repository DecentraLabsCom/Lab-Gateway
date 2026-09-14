from datetime import datetime, timezone

import pytest

from timeline_service import (
    build_reservation_timeline,
    fetch_latest_heartbeat,
    sanitize_limit,
    sanitize_offset,
    summarize_phases,
)


def test_timeline_pagination_normalization_preserves_defaults_and_clamps():
    assert sanitize_limit(None, default_limit=25, max_limit=100) == 25
    assert sanitize_limit("invalid", default_limit=25, max_limit=100) == 25
    assert sanitize_limit("0", default_limit=25, max_limit=100) == 1
    assert sanitize_limit("500", default_limit=25, max_limit=100) == 100
    assert sanitize_offset(None) == 0
    assert sanitize_offset("invalid") == 0
    assert sanitize_offset("-10") == 0
    assert sanitize_offset("4") == 4


class _MappedResult:
    def __init__(self, first=None, rows=()):
        self._first = first
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        return next(self.results)


class _Begin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _Begin(self.connection)


def test_fetch_latest_heartbeat_projects_public_shape_and_ignores_bad_raw_json():
    timestamp = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    connection = _Connection(
        [
            _MappedResult(
                {
                    "timestamp_utc": timestamp,
                    "ready": 1,
                    "local_mode": 0,
                    "local_session": 1,
                    "last_power_action_ts": None,
                    "last_power_action_mode": "on",
                    "last_forced_logoff_ts": timestamp,
                    "last_forced_logoff_user": "alice",
                    "raw_json": "not-json",
                }
            )
        ]
    )

    result = fetch_latest_heartbeat(
        connection,
        "lab-ws-01",
        sql_text=lambda value: value,
        json_loads=__import__("json").loads,
        to_iso=lambda value: value.isoformat() if value else None,
    )

    assert result == {
        "timestamp": timestamp.isoformat(),
        "ready": True,
        "localMode": False,
        "localSession": True,
        "lastPower": {"timestamp": None, "mode": "on"},
        "lastForcedLogoff": {"timestamp": timestamp.isoformat(), "user": "alice"},
        "raw": None,
    }


def test_summarize_phases_selects_latest_entry_for_each_phase():
    operations = [
        {"action": "wake", "status": "failed"},
        {"action": "power:on", "status": "completed"},
        {"action": "wake", "status": "completed"},
        {"action": "scheduler:end", "status": "completed"},
    ]

    result = summarize_phases(operations)

    assert result["wake"] == operations[2]
    assert result["power"] == operations[1]
    assert result["prepare"] is None
    assert result["schedulerEnd"] == operations[3]


def test_build_reservation_timeline_preserves_pagination_and_missing_reservation():
    reservation = {
        "transaction_hash": "reservation-1",
        "lab_id": "lab-1",
        "status": "CONFIRMED",
        "start_time": None,
        "end_time": None,
        "wallet_address": "0xabc",
        "created_at": None,
        "updated_at": None,
    }
    rows = [{"action": "wake", "status": "completed", "success": 1}]
    connection = _Connection(
        [
            _MappedResult(reservation),
            _ScalarResult(1),
            _MappedResult(rows=rows),
            _MappedResult(rows=list(reversed(rows))),
        ]
    )

    result = build_reservation_timeline(
        "reservation-1",
        2,
        0,
        engine=_Engine(connection),
        host_by_lab=lambda _lab_id: {"name": "lab-ws-01"},
        sql_text=lambda value: value,
        rows_to_operations=lambda received: received,
        to_iso=lambda value: value.isoformat() if value else None,
        phase_lookback=10,
        fetch_latest_heartbeat=lambda *_args: None,
        summarize_phases=summarize_phases,
    )

    assert result["reservation"]["reservationId"] == "reservation-1"
    assert result["pagination"] == {
        "limit": 2,
        "offset": 0,
        "page": 1,
        "pageSize": 2,
        "returned": 1,
        "total": 1,
        "hasMore": False,
        "nextOffset": 1,
    }

    missing_connection = _Connection([_MappedResult(None)])
    with pytest.raises(LookupError, match="Reservation not found"):
        build_reservation_timeline(
            "missing",
            2,
            0,
            engine=_Engine(missing_connection),
            host_by_lab=lambda _lab_id: None,
            sql_text=lambda value: value,
            rows_to_operations=lambda received: received,
            to_iso=lambda value: None,
            phase_lookback=10,
            fetch_latest_heartbeat=lambda *_args: None,
            summarize_phases=summarize_phases,
        )
