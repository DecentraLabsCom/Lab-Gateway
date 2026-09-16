from host_inventory_service import (
    build_host_inventory_from_sources,
    find_unique_host_for_connection,
)


class _Lock:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        self.calls.append("lock-enter")
        return self

    def __exit__(self, *_args):
        self.calls.append("lock-exit")
        return False


def test_build_host_inventory_from_sources_preserves_collection_order_and_lock_scope():
    calls = []
    hosts = [{"name": "lab-01"}]
    registry = type(
        "Registry",
        (),
        {"all_hosts": lambda self: calls.append("hosts") or hosts},
    )()

    result = build_host_inventory_from_sources(
        registry,
        hosts_lock=_Lock(calls),
        load_dynamic_config=lambda: calls.append("dynamic") or {"hosts": []},
        load_guacamole_connections=lambda: calls.append("guacamole") or ([], None),
        normalize_key=lambda value: str(value or "").lower(),
        safe_entry=lambda host, *, editable=False: {"name": host["name"], "editable": editable},
    )

    assert calls == ["lock-enter", "hosts", "lock-exit", "dynamic", "guacamole"]
    assert result["hosts"] == [{"name": "lab-01", "editable": False, "guacamole": {"status": "none", "connections": []}}]


def test_find_unique_host_for_connection_matches_registered_name_or_address():
    hosts = [
        {"name": "station-01", "address": "192.168.1.50", "labs": []},
        {"name": "station-02", "address": "192.168.1.51", "labs": ["legacy-lab"]},
    ]

    result = find_unique_host_for_connection(
        hosts,
        {"id": 5, "hostname": "192.168.1.50"},
        normalize_key=lambda value: str(value or "").strip().lower(),
    )

    assert result is hosts[0]


def test_find_unique_host_for_connection_returns_none_without_a_unique_match():
    hosts = [
        {"name": "station-01", "address": "192.168.1.50"},
        {"name": "station-02", "address": "192.168.1.50"},
    ]
    normalize_key = lambda value: str(value or "").strip().lower()

    assert find_unique_host_for_connection(
        hosts,
        {"id": 5, "hostname": "192.168.1.51"},
        normalize_key=normalize_key,
    ) is None
    assert find_unique_host_for_connection(
        hosts,
        {"id": 5, "hostname": "192.168.1.50"},
        normalize_key=normalize_key,
    ) is None
    assert find_unique_host_for_connection(
        hosts,
        {"id": 5, "hostname": ""},
        normalize_key=normalize_key,
    ) is None
