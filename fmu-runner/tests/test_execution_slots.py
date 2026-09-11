import pytest
from fastapi import HTTPException

from execution_slots import ConcurrencySlots


def test_concurrency_slots_acquire_and_release_track_each_lab():
    slots = ConcurrencySlots()

    slots.acquire("42", 1)
    assert slots.counts["42"] == 1

    slots.release("42")
    assert slots.counts["42"] == 0


def test_concurrency_slots_rejects_when_limit_is_reached():
    slots = ConcurrencySlots()
    slots.acquire("42", 1)

    with pytest.raises(HTTPException) as error:
        slots.acquire("42", 1)

    assert error.value.status_code == 429
    assert error.value.detail == (
        "Concurrency limit (1) reached for this FMU. Try again shortly."
    )


def test_concurrency_slots_release_never_goes_negative():
    slots = ConcurrencySlots()

    slots.release("42")
    slots.release("42")

    assert slots.counts["42"] == 0