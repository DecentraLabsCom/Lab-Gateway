from claim_values import (
    claim_reservation_key,
    coerce_epoch_seconds,
    get_claim_lab_id,
    normalize_lab_id,
)


def test_normalize_lab_id_strips_values_and_returns_none_for_empty():
    assert normalize_lab_id(" 42 ") == "42"
    assert normalize_lab_id(7) == "7"
    assert normalize_lab_id("   ") is None
    assert normalize_lab_id(None) is None


def test_get_claim_lab_id_uses_normalization():
    assert get_claim_lab_id({"labId": " 42 "}) == "42"
    assert get_claim_lab_id({"labId": ""}) is None


def test_claim_reservation_key_normalizes_missing_and_case_values():
    assert claim_reservation_key({"reservationKey": "  RES-1 "}) == "res-1"
    assert claim_reservation_key({}) == ""


def test_coerce_epoch_seconds_handles_numeric_values_only():
    assert coerce_epoch_seconds(12.9) == 12
    assert coerce_epoch_seconds(" 12.9 ") == 12
    assert coerce_epoch_seconds(12) == 12
    assert coerce_epoch_seconds(True) is None
    assert coerce_epoch_seconds("not-a-timestamp") is None
    assert coerce_epoch_seconds(None) is None