from types import SimpleNamespace

from wol_runtime import WolRuntime, create_wol_runtime


def test_wol_runtime_forwards_network_callbacks_and_optional_port():
    calls = []
    providers = {
        "_wol_and_wait_impl": lambda *args, **kwargs: calls.append((args, kwargs)) or (True, 2),
        "send_magic_packet": "magic",
        "time": SimpleNamespace(sleep="sleep"),
        "host_is_up": "up",
    }
    runtime = create_wol_runtime(providers)

    assert isinstance(runtime, WolRuntime)
    assert runtime.wol_and_wait("AA:BB", None, 9, "host", 3, 0.5, 5986) == (True, 2)
    assert calls == [
        (
            ("AA:BB", None, 9, "host", 3, 0.5),
            {
                "probe_port": 5986,
                "send_magic_packet": "magic",
                "sleep": "sleep",
                "host_is_up": "up",
            },
        )
    ]
