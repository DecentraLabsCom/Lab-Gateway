import pytest
from fastapi import HTTPException

from timeout_policy import effective_timeout_seconds


def test_effective_timeout_caps_to_configured_max_without_expiration():
    assert effective_timeout_seconds(400, max_timeout=300, exp_ts=None, now=1000.0) == 300


def test_effective_timeout_caps_to_expiration_window():
    assert effective_timeout_seconds(120, max_timeout=300, exp_ts=1005, now=1000.0) == 5


def test_effective_timeout_rejects_expired_window():
    with pytest.raises(HTTPException) as error:
        effective_timeout_seconds(120, max_timeout=300, exp_ts=999, now=1000.0)

    assert error.value.status_code == 401
    assert error.value.detail == "Reservation token has expired"