from input_runtime import InputRuntime, create_input_runtime


def test_input_runtime_forwards_normalizers_and_defaults_dynamically():
    calls = []
    providers = {
        "_coerce_bool_impl": lambda value: calls.append(("bool", value)) or True,
        "_parse_bool_impl": lambda value, default: calls.append(
            ("parse", value, default)
        ) or default,
        "_normalize_args_impl": lambda value, default=None: calls.append(
            ("args", value, default)
        ) or ["normalized"],
        "_parse_recipients_impl": lambda value, default=None: calls.append(
            ("recipients", value, default)
        ) or ["recipient"],
    }
    runtime = create_input_runtime(providers)

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
