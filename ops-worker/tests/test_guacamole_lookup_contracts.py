import worker


def test_guacamole_name_candidates_contract_preserves_order_and_fallback(monkeypatch):
    connection = {"hostname": "LAB-01", "name": "Configured name"}
    connections = [
        {"id": 1, "hostname": "lab-01", "name": "Primary"},
        {"id": 2, "hostname": "LAB-01", "name": "Primary"},
        {"id": 3, "hostname": "lab-01", "name": "Backup"},
        {"id": 4, "hostname": "other", "name": "Other"},
        {"id": 5, "hostname": "lab-01", "name": ""},
    ]
    calls = []

    def load_connections():
        calls.append("load")
        return connections, None

    monkeypatch.setattr(worker, "load_guacamole_connections", load_connections)
    monkeypatch.setattr(worker, "normalize_match_key", lambda value: str(value or "").strip().lower())

    assert worker.guacamole_name_candidates(connection) == [
        "Primary",
        "Backup",
        "lab-01",
        "LAB-01",
    ]
    assert calls == ["load"]


def test_guacamole_name_candidates_contract_uses_name_when_hostname_is_empty(monkeypatch):
    monkeypatch.setattr(
        worker,
        "load_guacamole_connections",
        lambda: ([{"hostname": "other", "name": "Other"}], None),
    )
    monkeypatch.setattr(worker, "normalize_match_key", lambda value: str(value or "").strip().lower())

    assert worker.guacamole_name_candidates({"hostname": "", "name": "Fallback name"}) == [
        "Fallback name"
    ]


def test_resolve_guacamole_connection_contract_converts_id_and_returns_matching_row(monkeypatch):
    connections = [{"id": 7, "name": "RDP Lab"}, {"id": 8, "name": "Other"}]
    calls = []

    def load_connections():
        calls.append("load")
        return connections, None

    monkeypatch.setattr(worker, "load_guacamole_connections", load_connections)

    assert worker.resolve_guacamole_connection("7") == connections[0]
    assert calls == ["load"]


def test_resolve_guacamole_connection_contract_does_not_load_for_invalid_id(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "load_guacamole_connections", lambda: calls.append("load"))

    assert worker.resolve_guacamole_connection("not-an-id") is None
    assert calls == []


def test_resolve_guacamole_connection_contract_returns_none_when_id_is_unknown(monkeypatch):
    monkeypatch.setattr(
        worker,
        "load_guacamole_connections",
        lambda: ([{"id": 7, "name": "RDP Lab"}], None),
    )

    assert worker.resolve_guacamole_connection(999) is None
