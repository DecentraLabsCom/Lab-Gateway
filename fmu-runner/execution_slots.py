from threading import Lock

from fastapi import HTTPException


class ConcurrencySlots:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.lock = Lock()

    def acquire(self, lab_id: str, limit: int) -> None:
        with self.lock:
            current = self.counts.setdefault(lab_id, 0)
            if current >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Concurrency limit ({limit}) reached for this FMU. Try again shortly.",
                )
            self.counts[lab_id] = current + 1

    def release(self, lab_id: str) -> None:
        with self.lock:
            self.counts[lab_id] = max(0, self.counts.get(lab_id, 0) - 1)