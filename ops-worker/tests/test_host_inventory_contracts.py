import worker


def test_build_host_inventory_contract_preserves_sources_matching_and_public_shape(
    monkeypatch,
):
    hosts = [
        {"name": "lab-ws-01", "address": "192.168.1.50"},
        {"name": "lab-ws-02", "address": "192.168.1.51"},
    ]
    connections = [
        {"id": 7, "hostname": "lab-ws-01", "name": "Primary"},
        {"id": 8, "hostname": "other-host", "name": "Other"},
    ]
    calls = []

    class FakeRegistry:
        def all_hosts(self):
            calls.append(("hosts",))
            return hosts

    def load_dynamic_config():
        calls.append(("dynamic",))
        return {"hosts": [{"name": "lab-ws-02"}]}

    def load_guacamole_connections():
        calls.append(("guacamole",))
        return connections, None

    def safe_entry(host, *, editable=False):
        calls.append(("entry", host, editable))
        return {"name": host["name"], "editable": editable}

    monkeypatch.setattr(worker, "HOSTS", FakeRegistry())
    monkeypatch.setattr(worker, "load_dynamic_config", load_dynamic_config)
    monkeypatch.setattr(worker, "load_guacamole_connections", load_guacamole_connections)
    monkeypatch.setattr(worker, "safe_host_inventory_entry", safe_entry)

    result = worker.build_host_inventory()

    assert calls == [
        ("hosts",),
        ("dynamic",),
        ("guacamole",),
        ("entry", hosts[0], False),
        ("entry", hosts[1], True),
    ]
    assert result == {
        "hosts": [
            {
                "name": "lab-ws-01",
                "editable": False,
                "guacamole": {
                    "status": "single",
                    "connections": [connections[0]],
                },
            },
            {
                "name": "lab-ws-02",
                "editable": True,
                "guacamole": {
                    "status": "none",
                    "connections": [],
                },
            },
        ],
        "guacamoleAvailable": True,
        "guacamoleError": None,
        "guacamoleUnmatched": [connections[1]],
    }


def test_build_host_inventory_contract_preserves_guacamole_error_state(monkeypatch):
    monkeypatch.setattr(
        worker,
        "HOSTS",
        type("Registry", (), {"all_hosts": lambda _self: []})(),
    )
    monkeypatch.setattr(worker, "load_dynamic_config", lambda: {"hosts": []})
    monkeypatch.setattr(
        worker,
        "load_guacamole_connections",
        lambda: ([], "Guacamole database unavailable"),
    )

    assert worker.build_host_inventory() == {
        "hosts": [],
        "guacamoleAvailable": False,
        "guacamoleError": "Guacamole database unavailable",
        "guacamoleUnmatched": [],
    }
