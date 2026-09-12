import worker


def test_parse_bool_contract_handles_defaults_booleans_and_string_tokens():
    assert worker.parse_bool(None, True) is True
    assert worker.parse_bool(None, False) is False
    assert worker.parse_bool(True, False) is True
    assert worker.parse_bool(False, True) is False
    assert worker.parse_bool(" FALSE ", True) is False
    assert worker.parse_bool("0", True) is False
    assert worker.parse_bool("no", True) is False
    assert worker.parse_bool("off", True) is False
    assert worker.parse_bool("falsey", False) is True


def test_parse_bool_contract_uses_python_truthiness_for_other_values():
    assert worker.parse_bool(1, False) is True
    assert worker.parse_bool(0, True) is False
    assert worker.parse_bool([], True) is False


def test_normalize_args_contract_copies_defaults_and_stringifies_lists():
    default = ["--default"]

    result = worker.normalize_args(None, default)

    assert result == ["--default"]
    assert result is not default
    assert worker.normalize_args([1, None, "--flag"]) == ["1", "None", "--flag"]


def test_normalize_args_contract_wraps_scalar_values():
    assert worker.normalize_args("--flag") == ["--flag"]
    assert worker.normalize_args(7) == ["7"]
    assert worker.normalize_args(None) == []


def test_parse_recipients_contract_splits_and_strips_list_items():
    assert worker.parse_recipients([
        " alice@example.com, bob@example.com ",
        "",
        "carol@example.com,,alice@example.com",
    ]) == [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
        "alice@example.com",
    ]


def test_parse_recipients_contract_handles_scalar_and_default_values():
    default = ["default@example.com"]

    result = worker.parse_recipients(None, default)

    assert result == default
    assert result is not default
    assert worker.parse_recipients(" alice@example.com, ") == ["alice@example.com"]
