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
        resolve_lab_status_targets=lambda: [{
            "labId": "7",
            "hostName": "private-host",
            "hostname": "private-host",
            "protocol": "rdp",
            "port": "3389",
        }],
        fetch_latest_heartbeat=lambda connection, host_name: calls.append(host_name) or heartbeat,
        probe_lab_targets=lambda targets: {},
        now=now,
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "ready"
    assert result["statuses"][1]["state"] == "unknown"
    assert calls == ["private-host"]
    assert engine.connection.closed is True
    assert "private-host" not in str(result)


def test_build_response_uses_guacamole_probe_for_lab_without_station_mapping():
    engine = Engine()
    now = lambda: datetime(2026, 9, 23, 10, 0, 30, tzinfo=timezone.utc)
    probed = []

    result = build_public_lab_status_response(
        ["8"],
        engine=engine,
        resolve_lab_associations=lambda: [],
        resolve_lab_status_targets=lambda: [{
            "labId": "8",
            "connectionId": "9",
            "hostname": "linux-only",
            "protocol": "ssh",
            "port": "22",
        }],
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(
            AssertionError("a lab without a Station mapping must not read heartbeats")
        ),
        probe_lab_targets=lambda targets: probed.append(targets) or {
            "8": {
                "signal": "reachable",
                "reason": "target_reachable",
                "source": "guacamole_tcp_probe",
                "observedAt": "2026-09-23T10:00:20+00:00",
            }
        },
        now=now,
        max_age_seconds=180,
    )

    assert result["statuses"][0]["state"] == "reachable"
    assert result["statuses"][0]["source"] == "guacamole_tcp_probe"
    assert probed[0][0]["hostname"] == "linux-only"
    assert "linux-only" not in str(result)
