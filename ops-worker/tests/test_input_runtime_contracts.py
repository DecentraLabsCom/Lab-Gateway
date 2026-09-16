from dataclasses import FrozenInstanceError

import pytest

from input_context import InputContext
from input_runtime import InputRuntime, create_input_runtime


def _context(**overrides):
    calls = overrides.pop("calls", [])
    values = {
        "coerce_bool": lambda value: calls.append(("bool", value)) or True,
        "parse_bool": lambda value, default: calls.append(
            ("parse", value, default)
        ) or default,
        "normalize_args": lambda value, default=None: calls.append(
            ("args", value, default)
        ) or ["normalized"],
        "parse_recipients": lambda value, default=None: calls.append(
            ("recipients", value, default)
        ) or ["recipient"],
    }
    values.update(overrides)
    return InputContext(**values), calls


def test_input_runtime_forwards_explicit_normalizers_and_defaults():
    calls = []
    context, _ = _context(calls=calls)
    runtime = create_input_runtime(context)

    assert isinstance(runtime, InputRuntime)
    assert runtime.coerce_bool("yes") is True
    assert runtime.parse_bool(None, False) is False
    assert runtime.normalize_args(None, ["default"]) == ["normalized"]
    assert runtime.parse_recipients(None, ["default@example.com"]) == ["recipient"]
    assert calls == [
        ("bool", "yes"),
        ("parse", None, False),
        ("args", None, ["default"]),
        ("recipients", None, ["default@example.com"]),
    ]


def test_input_context_is_immutable():
    context, _ = _context()

    with pytest.raises(FrozenInstanceError):
        setattr(context, "parse_bool", lambda value, default: default)
