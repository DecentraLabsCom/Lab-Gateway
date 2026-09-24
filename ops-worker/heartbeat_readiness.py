"""Capability-specific readiness helpers for Lab Station heartbeats."""

from collections.abc import Mapping
from typing import Any, Optional


def capability_ready(
    heartbeat: Mapping[str, Any] | None,
    capability: str,
) -> Optional[bool]:
    """Return readiness for one capability, with legacy-heartbeat fallback.

    New Lab Station versions publish ``readiness`` at the heartbeat root.
    During the rollout, accept the same block nested under ``status`` and
    finally fall back to the historic root-level ``ready`` field.
    """
    if not isinstance(heartbeat, Mapping):
        return None

    readiness = heartbeat.get("readiness")
    if not isinstance(readiness, Mapping):
        status = heartbeat.get("status")
        readiness = status.get("readiness") if isinstance(status, Mapping) else None
    entry = readiness.get(capability) if isinstance(readiness, Mapping) else None
    if isinstance(entry, Mapping) and isinstance(entry.get("ready"), bool):
        return entry["ready"]

    legacy = heartbeat.get("ready")
    if not isinstance(legacy, bool):
        summary = heartbeat.get("summary")
        legacy = summary.get("ready") if isinstance(summary, Mapping) else None
    return legacy if isinstance(legacy, bool) else None


__all__ = ["capability_ready"]
