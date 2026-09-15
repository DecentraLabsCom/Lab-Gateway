from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from wol_context import WolContext
from wol_runtime import WolRuntime, create_wol_runtime


def test_wol_runtime_forwards_network_callbacks_and_optional_port():
    calls = []
    context = WolContext(
        wol_and_wait=lambda *args, **kwargs: calls.append((args, kwargs)) or (True, 2),
        get_send_magic_packet=lambda: "magic",
        get_sleep=lambda: "sleep",
        get_host_is_up=lambda: "up",
    )
    runtime = create_wol_runtime(context)

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


def test_wol_context_is_immutable():
    context = WolContext(
        wol_and_wait=lambda *args, **kwargs: (False, 0),
        get_send_magic_packet=lambda: SimpleNamespace(),
        get_sleep=lambda: SimpleNamespace(),
        get_host_is_up=lambda: SimpleNamespace(),
    )

    with pytest.raises(FrozenInstanceError):
        context.get_sleep = lambda: None
