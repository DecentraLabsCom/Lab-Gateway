"""Capability-specific readiness helpers for Lab Station heartbeats."""

from collections.abc import Mapping
from typing import Any, Optional


def capability_ready(
    heartbeat: Mapping[str, Any] | None,
    capability: str,
) -> Optional[bool]:
    """Return readiness for one capability, with legacy-heartbeat fallback.

    New Lab Station versions publish ``readiness`` at the heartbeat root.
    During the rollout, accept the same block nested under ``status``. The
    legacy summary/root ``ready`` value is meaningful only for the profile's
    primary capability: physical lab for physical profiles, FMU for fmu-only.
    """
    if not isinstance(heartbeat, Mapping):
        return None

    station = heartbeat.get("station")
    source = station if isinstance(station, Mapping) else heartbeat
    readiness = source.get("readiness")
    status = source.get("status")
    if not isinstance(readiness, Mapping):
        readiness = status.get("readiness") if isinstance(status, Mapping) else None
    entry = readiness.get(capability) if isinstance(readiness, Mapping) else None
    if isinstance(entry, Mapping) and isinstance(entry.get("ready"), bool):
        return entry["ready"]

    profile = source.get("profile")
    if profile is None and isinstance(status, Mapping):
        profile = status.get("profile")
    primary_capability = "fmu" if profile == "fmu-only" else "physicalLab"
    if capability != primary_capability:
        return None

    legacy = source.get("ready")
    if not isinstance(legacy, bool):
        summary = source.get("summary")
        if not isinstance(summary, Mapping) and isinstance(status, Mapping):
            summary = status.get("summary")
        legacy = summary.get("ready") if isinstance(summary, Mapping) else None
    return legacy if isinstance(legacy, bool) else None


__all__ = ["capability_ready"]
