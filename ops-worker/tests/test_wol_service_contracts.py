from wol_service import wol_and_wait


def test_wol_and_wait_contract_preserves_retry_order_and_arguments():
    packets = []
    sleeps = []
    probes = iter([False, True])

    result = wol_and_wait(
        "00:11:22:33:44:55",
        None,
        9,
        "lab-ws-01",
        3,
        0.5,
        probe_port=5986,
        send_magic_packet=lambda *args, **kwargs: packets.append((args, kwargs)),
        sleep=lambda seconds: sleeps.append(seconds),
        host_is_up=lambda *args, **kwargs: (args, kwargs, next(probes))[2],
    )

    assert result == (True, 2)
    assert packets == [
        (("00:11:22:33:44:55",), {"ip_address": "255.255.255.255", "port": 9}),
        (("00:11:22:33:44:55",), {"ip_address": "255.255.255.255", "port": 9}),
    ]
    assert sleeps == [0.5, 0.5]


def test_wol_and_wait_contract_returns_attempt_count_when_all_probes_fail():
    calls = []

    assert wol_and_wait(
        "00:11:22:33:44:55",
        "192.168.1.255",
        7,
        "lab-ws-01",
        2,
        0,
        send_magic_packet=lambda *args, **kwargs: calls.append((args, kwargs)),
        sleep=lambda _seconds: None,
        host_is_up=lambda *_args, **_kwargs: False,
    ) == (False, 2)
    assert len(calls) == 2
