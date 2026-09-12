import worker


def test_reload_hosts_contract_preserves_registry_refresh_and_automator_update(
    monkeypatch,
):
    calls = []
    config = {"hosts": [{"name": "lab-ws-01", "address": "192.168.1.50"}]}
    old_registry = worker.HOSTS
    monkeypatch.setattr(worker, "HOSTS", old_registry)

    class FakeRegistry:
        def __init__(self, received_config):
            calls.append(("registry", received_config))

        def all_hosts(self):
            calls.append(("all_hosts",))
            return config["hosts"]

        def count(self):
            calls.append(("count",))
            return 1

    class FakeAutomator:
        registry = old_registry

    automator = FakeAutomator()

    monkeypatch.setattr(worker, "load_config", lambda: calls.append(("load",)) or config)
    monkeypatch.setattr(worker, "HostRegistry", FakeRegistry)
    monkeypatch.setattr(
        worker,
        "refresh_winrm_trust_store",
        lambda hosts: calls.append(("trust", hosts)),
    )
    monkeypatch.setattr(worker, "RESERVATION_AUTOMATOR", automator)

    result = worker.reload_hosts()

    assert result == (1, None)
    assert calls == [
        ("load",),
        ("registry", config),
        ("all_hosts",),
        ("trust", config["hosts"]),
        ("count",),
        ("count",),
    ]
    assert isinstance(worker.HOSTS, FakeRegistry)
    assert automator.registry is worker.HOSTS


def test_reload_hosts_contract_fails_closed_without_replacing_registry(monkeypatch):
    old_registry = worker.HOSTS
    calls = []

    monkeypatch.setattr(
        worker,
        "load_config",
        lambda: (_ for _ in ()).throw(ValueError("invalid catalog")),
    )
    monkeypatch.setattr(
        worker,
        "refresh_winrm_trust_store",
        lambda hosts: calls.append(hosts),
    )

    result = worker.reload_hosts()

    assert result == (0, "Host catalog reload failed")
    assert worker.HOSTS is old_registry
    assert calls == []
