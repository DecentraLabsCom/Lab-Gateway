"""Pure projection of the last Lab Station heartbeat into a public status."""

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_status(lab_id: Any, now: datetime, *, state: str, reason: str) -> Dict[str, Any]:
    return {
        "labId": str(lab_id),
        "state": state,
        "reason": reason,
        "source": "lab_station_heartbeat",
        "observedAt": None,
        "ageSeconds": None,
        "severity": "neutral" if state == "unknown" else "critical" if state == "not_ready" else "warning",
        "generatedAt": _iso(now),
    }


def project_lab_status(
    lab_id: Any,
    heartbeat: Optional[Mapping[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int,
    host_mapped: bool = True,
) -> Dict[str, Any]:
    """Return a bounded, user-facing status from one persisted heartbeat.

    A heartbeat is trusted only while it is fresh.  Local mode/session flags
    take precedence over readiness because they mean the station is alive but
    the remote access lane is currently occupied or deliberately blocked.
    """
    current = _as_utc(now) or datetime.now(timezone.utc)
    if not host_mapped:
        return _base_status(lab_id, current, state="unknown", reason="lab_not_mapped")
    if not heartbeat:
        return _base_status(lab_id, current, state="unknown", reason="heartbeat_missing")

    observed = _as_utc(heartbeat.get("timestamp"))
    if observed is None:
        return _base_status(lab_id, current, state="unknown", reason="heartbeat_invalid")

    age_seconds = max(0, int((current - observed).total_seconds()))
    result = {
        **_base_status(lab_id, current, state="unknown", reason="heartbeat_stale"),
        "observedAt": _iso(observed),
        "ageSeconds": age_seconds,
    }
    if age_seconds > max(30, int(max_age_seconds)):
        return result

    local_mode = heartbeat.get("localMode") is True
    local_session = heartbeat.get("localSession") is True
    if local_mode or local_session:
        result.update({
            "state": "busy",
            "reason": "local_mode_enabled" if local_mode else "local_session_active",
            "severity": "critical" if local_mode else "warning",
        })
        return result

    if heartbeat.get("ready") is True:
        result.update({"state": "ready", "reason": "station_ready", "severity": "positive"})
    else:
        result.update({"state": "not_ready", "reason": "station_not_ready", "severity": "critical"})
    return result


__all__ = ["project_lab_status"]
