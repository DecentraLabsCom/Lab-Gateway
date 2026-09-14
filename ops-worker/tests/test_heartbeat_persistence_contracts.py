import json
from datetime import datetime, timezone

from heartbeat_persistence import load_persisted_heartbeat, persist_heartbeat


class _Result:
    def __init__(self, row=None, lastrowid=None):
        self.row = row
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, host_row=None):
        self.host_row = host_row
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        if len(self.calls) == 1:
            return _Result(self.host_row)
        if "INSERT INTO lab_hosts" in statement:
            return _Result(lastrowid=42)
        return _Result()


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


def test_load_persisted_heartbeat_returns_raw_payload_by_host_name():
    connection = _Connection()
    heartbeat = {"raw": {"summary": {"ready": True}}}
    calls = []

    result = load_persisted_heartbeat(
        _Engine(connection),
        "lab-01",
        {"name": "lab-ws-01"},
        fetch_latest_heartbeat=lambda conn, host_name: calls.append((conn, host_name)) or heartbeat,
    )

    assert result == heartbeat["raw"]
    assert calls == [(connection, "lab-ws-01")]


def test_load_persisted_heartbeat_is_closed_when_engine_or_raw_payload_is_missing():
    assert load_persisted_heartbeat(
        None,
        "lab-01",
        {"name": "lab-ws-01"},
        fetch_latest_heartbeat=lambda *_args: (_ for _ in ()).throw(AssertionError()),
    ) is None
    assert load_persisted_heartbeat(
        _Engine(_Connection()),
        "lab-01",
        {"name": "lab-ws-01"},
        fetch_latest_heartbeat=lambda *_args: {},
    ) is None


def test_worker_aas_heartbeat_facade_keeps_dynamic_database_callback(monkeypatch):
    import worker

    connection = _Connection()
    monkeypatch.setattr(worker, "DB_ENGINE", _Engine(connection))
    monkeypatch.setattr(
        worker,
        "_fetch_latest_heartbeat",
        lambda conn, host_name: {"raw": {"host": host_name}},
    )

    assert worker._load_aas_persisted_heartbeat(
        "lab-01",
        {"name": "lab-ws-01"},
    ) == {"host": "lab-ws-01"}


def _persist(connection, host, heartbeat, last_event):
    return persist_heartbeat(
        _Engine(connection),
        host,
        heartbeat,
        last_event,
        to_utc=lambda value: datetime.fromisoformat(value) if value else None,
        now=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        sql_text=lambda value: value,
        json_dumps=json.dumps,
    )


def test_persist_heartbeat_inserts_host_heartbeat_and_event_with_projected_fields():
    connection = _Connection()
    heartbeat = {
        "timestamp": "2026-09-14T11:59:00+00:00",
        "summary": {"ready": True},
        "status": {"localModeEnabled": True, "localSessionActive": False},
        "operations": {
            "lastForcedLogoff": {"timestamp": "2026-09-14T11:58:00+00:00", "user": "alice"},
            "lastPowerAction": {"timestamp": "2026-09-14T11:57:00+00:00", "mode": "on"},
        },
    }
    event = {"timestamp": "2026-09-14T11:59:30+00:00", "kind": "logout"}

    _persist(
        connection,
        {"name": "lab-ws-01", "address": "192.168.1.50", "mac": "00:11:22:33:44:55"},
        heartbeat,
        event,
    )

    assert len(connection.calls) == 4
    assert "INSERT INTO lab_hosts" in connection.calls[1][0]
    assert connection.calls[1][1]["name"] == "lab-ws-01"
    heartbeat_params = connection.calls[2][1]
    assert heartbeat_params["host_id"] == 42
    assert heartbeat_params["ready"] is True
    assert heartbeat_params["local_mode"] is True
    assert heartbeat_params["local_session"] is False
    assert heartbeat_params["last_forced_user"] == "alice"
    assert json.loads(heartbeat_params["raw_json"]) == heartbeat
    event_params = connection.calls[3][1]
    assert event_params["kind"] == "session-guard"
    assert json.loads(event_params["payload"]) == event


def test_persist_heartbeat_updates_existing_host_and_skips_missing_event():
    connection = _Connection(host_row=(7,))
    heartbeat = {"timestamp": "2026-09-14T12:00:00+00:00", "summary": {"ready": False}}

    _persist(
        connection,
        {"name": "lab-ws-01", "address": "10.0.0.5", "mac": None},
        heartbeat,
        None,
    )

    assert len(connection.calls) == 3
    assert "UPDATE lab_hosts" in connection.calls[1][0]
    assert connection.calls[1][1] == {
        "address": "10.0.0.5",
        "mac": None,
        "last_seen": datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        "id": 7,
    }
