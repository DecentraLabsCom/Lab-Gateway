from pathlib import Path

import pytest

import session_observation_maintenance as maintenance


def test_reconciliation_command_delegates_to_explicit_runtime():
    calls = []

    class Runtime:
        def reconcile_guacamole_observations(self, token, source):
            calls.append((token, source))

        def close(self):
            calls.append("close")

    maintenance.run_reconciliation(
        "admin-token",
        "mysql",
        active_connections={},
        runtime_factory=lambda connections: calls.append(connections) or Runtime(),
    )

    assert calls == [{}, ("admin-token", "mysql"), "close"]


def test_reconciliation_command_closes_runtime_when_reconciliation_fails():
    calls = []

    class Runtime:
        def reconcile_guacamole_observations(self, _token, _source):
            calls.append("reconcile")
            raise RuntimeError("reconciliation failed")

        def close(self):
            calls.append("close")

    with pytest.raises(RuntimeError, match="reconciliation failed"):
        maintenance.run_reconciliation(
            "admin-token",
            "mysql",
            runtime_factory=lambda _connections: Runtime(),
        )

    assert calls == ["reconcile", "close"]


def test_build_runtime_closes_both_database_engines(monkeypatch):
    engines = []
    captured = {}

    class Engine:
        def __init__(self, dsn):
            self.dsn = dsn
            self.disposed = False
            engines.append(self)

        def dispose(self):
            self.disposed = True

    class Runtime:
        def create_service(self):
            return object()

    def capture_runtime(_context, *, close):
        captured["close"] = close
        return Runtime()

    monkeypatch.setattr(maintenance, "_engine", Engine)
    monkeypatch.setattr(
        maintenance,
        "create_session_observation_runtime",
        capture_runtime,
    )

    maintenance.build_runtime(
        environ={
            "MYSQL_DSN": "sqlite:///ops.db",
            "GUACAMOLE_MYSQL_DSN": "sqlite:///guacamole.db",
        }
    )

    captured["close"]()

    assert [engine.dsn for engine in engines] == [
        "sqlite:///ops.db",
        "sqlite:///guacamole.db",
    ]
    assert all(engine.disposed for engine in engines)


def test_reconciliation_command_does_not_import_worker_entrypoint():
    source = Path(maintenance.__file__).read_text(encoding="utf-8")

    assert "import worker" not in source
    assert "_reconcile_guacamole_observations" not in source


def test_command_main_parses_controlled_active_connections(monkeypatch):
    calls = []
    monkeypatch.setattr(
        maintenance,
        "run_reconciliation",
        lambda token, source, *, active_connections: calls.append(
            (token, source, active_connections)
        ),
    )

    assert maintenance.main(
        [
            "--admin-token",
            "admin-token",
            "--data-source",
            "mysql",
            "--active-connections-json",
            '{"connection": {"username": "lab-user"}}',
        ]
    ) == 0
    assert calls == [
        (
            "admin-token",
            "mysql",
            {"connection": {"username": "lab-user"}},
        )
    ]


def test_command_rejects_non_object_active_connections():
    with pytest.raises(ValueError, match="JSON object"):
        maintenance._parse_active_connections("[]")
