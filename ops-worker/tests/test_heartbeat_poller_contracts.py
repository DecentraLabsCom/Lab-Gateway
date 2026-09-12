import worker


def test_poll_all_hosts_contract_preserves_order_and_continues_after_failures(
    monkeypatch,
):
    hosts = [
        {"name": "lab-ws-01"},
        {"name": "lab-ws-02"},
        {"name": "lab-ws-03"},
    ]
    calls = []
    failure = RuntimeError("unreachable")

    class FakeRegistry:
        def all_hosts(self):
            calls.append(("all_hosts",))
            return hosts

    class FakeLogger:
        def info(self, *args):
            calls.append(("info", *args))

        def error(self, *args):
            calls.append(("error", *args))

    def poll(host, *, include_events):
        calls.append(("poll", host, include_events))
        if host["name"] == "lab-ws-02":
            raise failure

    monkeypatch.setattr(worker, "HOSTS", FakeRegistry())
    monkeypatch.setattr(worker, "poll_heartbeat", poll)
    monkeypatch.setattr(worker, "logging", FakeLogger())

    assert worker.poll_all_hosts() is None
    assert calls == [
        ("all_hosts",),
        ("poll", hosts[0], True),
        ("info", "Polled heartbeat for %s", "lab-ws-01"),
        ("poll", hosts[1], True),
        ("error", "Heartbeat poll failed for %s: %s", "lab-ws-02", failure),
        ("poll", hosts[2], True),
        ("info", "Polled heartbeat for %s", "lab-ws-03"),
    ]
