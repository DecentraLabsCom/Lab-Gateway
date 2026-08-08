"""Host-side unit checks for the Redis REST bridge protocol."""

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("redis-rest-server.py")
SPEC = importlib.util.spec_from_file_location("redis_rest_server", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_normalize_redis_value_preserves_nested_results():
    value = (b"ok", [b"one", None, 2], {b"field": b"value"})

    assert MODULE.normalize_redis_value(value) == [
        "ok",
        ["one", None, 2],
        {"field": "value"},
    ]
