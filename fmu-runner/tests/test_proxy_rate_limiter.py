from collections import defaultdict, deque
from threading import Lock

from proxy_rate_limiter import allow_download


def _state():
    return defaultdict(deque), Lock()


def test_allow_download_fails_closed_when_limit_is_disabled():
    hits, lock = _state()

    assert allow_download(
        "user-1:lab-1",
        limit_per_minute=0,
        hits=hits,
        lock=lock,
        clock=lambda: 100.0,
    ) is False
    assert dict(hits) == {}


def test_allow_download_accepts_until_limit_then_rejects():
    hits, lock = _state()
    clock = lambda: 100.0

    assert allow_download("user-1:lab-1", limit_per_minute=2, hits=hits, lock=lock, clock=clock)
    assert allow_download("user-1:lab-1", limit_per_minute=2, hits=hits, lock=lock, clock=clock)
    assert not allow_download("user-1:lab-1", limit_per_minute=2, hits=hits, lock=lock, clock=clock)


def test_allow_download_discards_hits_at_window_boundary():
    hits, lock = _state()
    times = iter((100.0, 100.0, 160.0))

    assert allow_download(
        "user-1:lab-1",
        limit_per_minute=2,
        hits=hits,
        lock=lock,
        clock=lambda: next(times),
    )
    assert allow_download(
        "user-1:lab-1",
        limit_per_minute=2,
        hits=hits,
        lock=lock,
        clock=lambda: next(times),
    )
    assert allow_download(
        "user-1:lab-1",
        limit_per_minute=2,
        hits=hits,
        lock=lock,
        clock=lambda: next(times),
    )
    assert list(hits["user-1:lab-1"]) == [160.0]
