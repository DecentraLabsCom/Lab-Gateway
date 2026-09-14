from network_probe import host_is_up, is_valid_ping_target, tcp_port_open


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_is_valid_ping_target_preserves_bounded_dns_validation():
    assert is_valid_ping_target("lab-ws-01") is True
    assert is_valid_ping_target("192.168.1.50") is True
    assert is_valid_ping_target("127.0.0.1; whoami") is False
    assert is_valid_ping_target("0." * 127 + "0") is False


def test_host_is_up_uses_the_configured_winrm_port_and_rejects_invalid_targets():
    calls = []
    warnings = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return _Connection()

    assert host_is_up(
        "lab-ws-01",
        1,
        probe_port=55986,
        is_valid_target=is_valid_ping_target,
        winrm_port=55986,
        create_connection=connect,
        warn=warnings.append,
    ) is True
    assert calls == [((("lab-ws-01", 55986),), {"timeout": 1.0})]

    assert host_is_up(
        "127.0.0.1; whoami",
        1,
        is_valid_target=is_valid_ping_target,
        winrm_port=55986,
        create_connection=connect,
        warn=warnings.append,
    ) is False
    assert len(calls) == 1
    assert warnings == ["Invalid reachability target rejected"]


def test_tcp_port_open_preserves_timeout_and_failure_contract():
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return _Connection()

    assert tcp_port_open(
        "lab-ws-01",
        5986,
        1.25,
        default_timeout=1.5,
        create_connection=connect,
    ) is True
    assert calls == [((("lab-ws-01", 5986), 1.25), {})]

    def fail(*_args, **_kwargs):
        raise OSError("offline")

    assert tcp_port_open(
        "lab-ws-01",
        5986,
        None,
        default_timeout=1.5,
        create_connection=fail,
    ) is False
