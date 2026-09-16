from threading import Lock
from typing import Any, Optional


SimulationEntry = tuple[Any, str, str, str, Optional[Any]]


class SimulationRegistry:
    def __init__(self):
        self.entries: dict[str, SimulationEntry] = {}
        self.lock = Lock()

    def register(
        self,
        sim_id: str,
        future: Any,
        lab_id: str,
        claims: dict,
        executor: Optional[Any] = None,
    ) -> None:
        entry: SimulationEntry = (
            future,
            lab_id,
            str(claims.get("reservationKey") or "").strip().lower(),
            str(claims.get("pucHash") or "").strip().lower(),
            executor,
        )
        with self.lock:
            self.entries[sim_id] = entry

    def get(self, sim_id: str) -> Optional[SimulationEntry]:
        with self.lock:
            return self.entries.get(sim_id)

    def pop(self, sim_id: str) -> Optional[SimulationEntry]:
        with self.lock:
            return self.entries.pop(sim_id, None)

    def count_for_lab(self, lab_id: str) -> int:
        """Return the number of currently tracked simulations for a lab."""
        normalized_lab_id = str(lab_id)
        with self.lock:
            return sum(
                1
                for entry in self.entries.values()
                if str(entry[1]) == normalized_lab_id
            )
