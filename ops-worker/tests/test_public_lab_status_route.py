from datetime import datetime, timezone

import pytest

from public_lab_status_route import build_public_lab_status_response, parse_lab_ids


def test_parse_lab_ids_accepts_repeated_and_comma_separated_values():
    assert parse_lab_ids(["1, 2", "2", "003"]) == ["1", "2", "3"]


def test_parse_lab_ids_rejects_empty_and_invalid_values():
    with pytest.raises(ValueError):
        parse_lab_ids([])
    with pytest.raises(ValueError):
        parse_lab_ids(["1,abc"])


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Engine:
    def __init__(self):
        self.connection = Connection()

    def connect(self):
        return self.connection


def test_build_response_reads_only_mapped_hosts_and_closes_connection():
    engine = Engine()
    heartbeat = {
        "timestamp": "2026-09-23T10:00:00+00:00",
        "ready": True,
        "localMode": False,
        "localSession": False,
    }
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)
    calls = []

    result = build_public_lab_status_response(
        ["7", "8"],
        engine=engine,
        resolve_lab_associations=lambda: [{"labId": "7", "hostName": "private-host"}],
        fetch_latest_heartbeat=lambda connection, host_name: calls.append(host_name) or heartbeat,
        now=now,
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "ready"
    assert result["statuses"][1]["state"] == "unknown"
    assert calls == ["private-host"]
    assert engine.connection.closed is True
    assert "private-host" not in str(result)
