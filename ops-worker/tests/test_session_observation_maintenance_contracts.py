from pathlib import Path

import pytest

import session_observation_maintenance as maintenance


def test_reconciliation_command_delegates_to_explicit_runtime():
    calls = []

    class Runtime:
        def reconcile_guacamole_observations(self, token, source):
            calls.append((token, source))

    maintenance.run_reconciliation(
        "admin-token",
        "mysql",
        active_connections={},
        runtime_factory=lambda connections: calls.append(connections) or Runtime(),
    )

    assert calls == [{}, ("admin-token", "mysql")]


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
