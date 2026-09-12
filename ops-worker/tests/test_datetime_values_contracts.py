from datetime import datetime, timezone

import worker


def test_to_utc_contract_handles_naive_and_zulu_timestamps():
    naive = worker.to_utc("2026-09-12T10:00:00")
    zulu = worker.to_utc("2026-09-12T10:00:00Z")

    assert naive == datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    assert zulu == datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def test_to_utc_contract_converts_offsets_and_returns_none_for_invalid_values():
    converted = worker.to_utc("2026-09-12T12:00:00+02:00")

    assert converted == datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    assert worker.to_utc(None) is None
    assert worker.to_utc("") is None
    assert worker.to_utc("not-a-timestamp") is None
