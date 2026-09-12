import worker


def test_get_mandatory_field_contract_uses_key_order_and_accepts_zero():
    payload = {"first": "", "second": 0, "third": "later"}

    assert worker._get_mandatory_field(payload, "first", "second", "third") == 0


def test_get_mandatory_field_contract_returns_first_present_value_without_coercion():
    value = {"nested": True}

    assert worker._get_mandatory_field(
        {"first": value, "second": "fallback"}, "first", "second"
    ) is value


def test_get_mandatory_field_contract_returns_none_when_values_are_missing_or_empty():
    assert worker._get_mandatory_field(
        {"first": None, "second": ""}, "first", "second", "third"
    ) is None


def test_canonical_demo_lab_id_contract_strips_and_canonicalizes_decimal_text():
    assert worker._canonical_demo_lab_id(" 00042 ") == "42"
    assert worker._canonical_demo_lab_id(42) == "42"
    assert worker._canonical_demo_lab_id("0") == "0"


def test_canonical_demo_lab_id_contract_rejects_non_decimal_values():
    assert worker._canonical_demo_lab_id(None) is None
    assert worker._canonical_demo_lab_id("") is None
    assert worker._canonical_demo_lab_id("  ") is None
    assert worker._canonical_demo_lab_id("42.0") is None
    assert worker._canonical_demo_lab_id("-1") is None
