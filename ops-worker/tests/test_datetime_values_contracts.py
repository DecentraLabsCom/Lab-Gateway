from datetime import datetime, timezone

import worker
from datetime_values import as_utc_datetime, to_iso


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


def test_as_utc_datetime_contract_preserves_datetime_and_string_normalization():
    naive = as_utc_datetime(
        "2026-09-12T10:00:00",
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    )
    offset = as_utc_datetime(
        "2026-09-12T12:00:00+02:00",
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    )

    assert naive == datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    assert offset == datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    assert as_utc_datetime(
        "invalid",
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    ) is None


def test_to_iso_contract_preserves_invalid_strings_and_formats_utc():
    timestamp = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)

    assert to_iso(
        timestamp,
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    ) == "2026-09-12T12:00:00+00:00"
    assert to_iso(
        "2026-09-12T10:00:00",
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    ) == "2026-09-12T10:00:00+00:00"
    assert to_iso(
        "invalid",
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    ) == "invalid"
    assert to_iso(
        None,
        parse_datetime=datetime.fromisoformat,
        utc_timezone=timezone.utc,
    ) is None
