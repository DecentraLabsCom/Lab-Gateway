from datetime import datetime, timezone

from demo_readiness_service import build_demo_readiness


class _Result:
    def __init__(self, value=None, rows=None):
        self.value = value
        self.rows = rows

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return self.rows or []


class _Connection:
    def __init__(self, results):
        self.results = iter(results)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, _statement, _params=None):
        return next(self.results)


class _Engine:
    def __init__(self, results):
        self.results = results

    def begin(self):
        return _Connection(self.results)


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args):
        self.warnings.append((message, args))


def _dependencies(**overrides):
    values = {
        "demo_lab_id": "",
        "demo_connection_id": "",
        "demo_user": "demo-user",
        "max_age_seconds": 180,
        "guacamole_db_engine": None,
        "db_engine": None,
        "find_host_by_lab": lambda _lab_id: None,
        "fetch_latest_heartbeat": lambda _conn, _host_name: None,
        "to_utc": lambda value: value,
        "sql_text": lambda statement: statement,
        "now": lambda: datetime.now(timezone.utc),
        "logger": _Logger(),
    }
    values.update(overrides)
    return values


def test_build_demo_readiness_contract_preserves_disabled_and_invalid_states():
    disabled = build_demo_readiness(**_dependencies())
    assert disabled["status"] == "disabled"

    invalid = build_demo_readiness(
        **_dependencies(demo_lab_id="not-a-number", demo_connection_id="7")
    )
    assert invalid["status"] == "misconfigured"


def test_build_demo_readiness_contract_preserves_ready_guacamole_and_station_checks():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    heartbeat = {"ready": True, "timestamp": now}
    guacamole = _Engine([
        _Result(1),
        _Result(1),
        _Result(rows=[{"connection_id": 7, "permission": "READ"}]),
    ])
    station = _Engine([])

    result = build_demo_readiness(
        **_dependencies(
            demo_lab_id="42",
            demo_connection_id="7",
            guacamole_db_engine=guacamole,
            db_engine=station,
            find_host_by_lab=lambda lab_id: {"name": f"lab-{lab_id}"},
            fetch_latest_heartbeat=lambda _conn, _host: heartbeat,
            now=lambda: now,
        )
    )

    assert result == {
        "status": "ready",
        "checks": {
            "connection": True,
            "principal": True,
            "permission": True,
            "physical_host": True,
        },
        "labId": "42",
        "connectionId": 7,
    }
