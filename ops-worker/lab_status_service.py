"""Pure projection of the last Lab Station heartbeat into a public status."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from heartbeat_readiness import capability_ready


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


def _merge_persisted_heartbeat(heartbeat: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Restore capability fields from the database heartbeat projection.

    The timeline/database boundary wraps the original Station heartbeat in
    ``raw`` while also exposing a few indexed fields at the top level.  Public
    status projection needs both: the indexed fields for legacy snapshots and
    the raw capability-specific readiness published by current Stations.
    """
    if not isinstance(heartbeat, Mapping):
        return heartbeat
    raw = heartbeat.get("raw")
    if not isinstance(raw, Mapping):
        return heartbeat

    merged = dict(heartbeat)
    merged.pop("raw", None)
    merged.update(raw)
    return merged


def _nested_status(heartbeat: Mapping[str, Any]) -> Mapping[str, Any]:
    status = heartbeat.get("status")
    return status if isinstance(status, Mapping) else {}


def _heartbeat_flag(heartbeat: Mapping[str, Any], top_level: str, nested: str) -> bool:
    if heartbeat.get(top_level) is True:
        return True
    return _nested_status(heartbeat).get(nested) is True


def session_projection(heartbeat: Mapping[str, Any]) -> Dict[str, Any]:
    legacy_local_session = (
        heartbeat.get("localSession") is True
        or _nested_status(heartbeat).get("localSessionActive") is True
    )
    sessions = heartbeat.get("sessions")
    if not isinstance(sessions, Mapping):
        sessions = _nested_status(heartbeat).get("sessions")
    if not isinstance(sessions, Mapping):
        return {
            "known": True,
            "active": legacy_local_session,
            "labUserActive": False,
            "remoteSessionActive": False,
            "reason": "local_session_active",
        }

    if sessions.get("queryOk") is False:
        return {"known": False, "active": False, "reason": "session_status_unavailable"}

    has_active = "active" in sessions
    active = sessions.get("active") is True if has_active else legacy_local_session
    lab_user_active = sessions.get("labUserActive") is True
    remote_active = sessions.get("remoteSessionActive") is True
    if lab_user_active:
        reason = "lab_user_session_active"
    elif remote_active:
        reason = "remote_session_active"
    else:
        reason = "local_session_active"
    return {
        "known": True,
        "active": active,
        "labUserActive": lab_user_active,
        "remoteSessionActive": remote_active,
        "reason": reason,
    }


def _base_status(
    lab_id: Any,
    now: datetime,
    *,
    state: str,
    reason: str,
    source: str = "lab_station_heartbeat",
) -> Dict[str, Any]:
    return {
        "labId": str(lab_id),
        "state": state,
        "reason": reason,
        "source": source,
        "observedAt": None,
        "ageSeconds": None,
        "severity": (
            "neutral"
            if state == "unknown"
            else "critical"
            if state == "not_ready"
            else "positive"
            if state == "reachable"
            else "warning"
        ),
        "generatedAt": _iso(now),
    }


def heartbeat_is_fresh(
    heartbeat: Optional[Mapping[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int,
) -> bool:
    """Return whether a persisted heartbeat is valid and within its freshness window."""
    if not heartbeat:
        return False
    observed = _as_utc(heartbeat.get("timestamp"))
    if observed is None:
        return False
    current = _as_utc(now) or datetime.now(timezone.utc)
    age_seconds = max(0, int((current - observed).total_seconds()))
    return age_seconds <= max(30, int(max_age_seconds))


def _project_target_probe(
    lab_id: Any,
    probe: Mapping[str, Any],
    current: datetime,
) -> Dict[str, Any]:
    signal = str(probe.get("signal") or "").strip().lower()
    reason = str(probe.get("reason") or "target_probe_error").strip()
    if reason not in {
        "target_reachable",
        "target_unreachable",
        "target_invalid",
        "target_probe_error",
    }:
        reason = "target_probe_error"
    observed = _as_utc(probe.get("observedAt"))
    if signal == "reachable":
        state = "reachable"
        severity = "positive"
    elif signal == "unreachable":
        state = "not_ready"
        severity = "critical"
    else:
        state = "unknown"
        severity = "neutral"
    result = {
        **_base_status(
            lab_id,
            current,
            state=state,
            reason=reason,
            source="guacamole_tcp_probe",
        ),
        "severity": severity,
    }
    if observed is not None:
        result.update({
            "observedAt": _iso(observed),
            "ageSeconds": max(0, int((current - observed).total_seconds())),
        })
    return result


def _project_fmu_runner_status(
    lab_id: Any,
    runner_status: Optional[Mapping[str, Any]],
    current: datetime,
) -> Dict[str, Any]:
    """Project local FMU runner health without exposing runner diagnostics."""
    status: Mapping[str, Any] = runner_status or {}
    signal = str(status.get("signal") or "unknown").strip().lower()
    if signal == "ready":
        state = "ready"
        severity = "positive"
    elif signal == "not_ready":
        state = "not_ready"
        severity = "critical"
    else:
        state = "unknown"
        severity = "neutral"
    reason = str(status.get("reason") or "fmu_runner_unavailable").strip()
    if reason not in {"fmu_ready", "fmu_not_ready", "fmu_runner_unavailable"}:
        reason = "fmu_runner_unavailable"
    result = {
        **_base_status(
            lab_id,
            current,
            state=state,
            reason=reason,
            source="fmu_runner_health",
        ),
        "severity": severity,
    }
    observed = _as_utc(status.get("observedAt"))
    if observed is not None:
        result.update({
            "observedAt": _iso(observed),
            "ageSeconds": max(0, int((current - observed).total_seconds())),
        })
    result["capabilities"] = {"fmu": result.copy()}
    return result


def _capability_ready(
    heartbeat: Mapping[str, Any],
    capability: str,
    fallback: bool,
) -> bool:
    """Read capability readiness while accepting pre-capability heartbeats."""
    ready = capability_ready(heartbeat, capability)
    return fallback if ready is None else ready


def _fresh_status(
    lab_id: Any,
    observed: Optional[datetime],
    age_seconds: int,
    current: datetime,
    *,
    ready: bool,
    reason_ready: str = "station_ready",
    reason_not_ready: str = "station_not_ready",
) -> Dict[str, Any]:
    result = {
        **_base_status(
            lab_id,
            current,
            state="ready" if ready else "not_ready",
            reason=reason_ready if ready else reason_not_ready,
        ),
        "severity": "positive" if ready else "critical",
        "observedAt": _iso(observed) if observed is not None else None,
        "ageSeconds": age_seconds,
    }
    return result


def project_lab_status(
    lab_id: Any,
    heartbeat: Optional[Mapping[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int,
    host_mapped: bool = True,
    target_probe: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a bounded, user-facing status from one persisted heartbeat.

    A heartbeat is trusted only while it is fresh.  Local mode/session flags
    take precedence over readiness because they mean the station is alive but
    the remote access lane is currently occupied or deliberately blocked.
    """
    heartbeat = _merge_persisted_heartbeat(heartbeat)
    current = _as_utc(now) or datetime.now(timezone.utc)
    if heartbeat is None:
        if target_probe is not None:
            return _project_target_probe(lab_id, target_probe, current)
        if not host_mapped:
            return _base_status(lab_id, current, state="unknown", reason="lab_not_mapped")
        return _base_status(lab_id, current, state="unknown", reason="heartbeat_missing")
    observed = _as_utc(heartbeat.get("timestamp")) if heartbeat else None
    age_seconds = (
        max(0, int((current - observed).total_seconds()))
        if observed is not None
        else None
    )
    heartbeat_fresh = (
        observed is not None
        and age_seconds is not None
        and age_seconds <= max(30, int(max_age_seconds))
    )
    if not heartbeat_fresh:
        if target_probe is not None:
            return _project_target_probe(lab_id, target_probe, current)
        if not host_mapped:
            return _base_status(lab_id, current, state="unknown", reason="lab_not_mapped")
        if not heartbeat:
            return _base_status(lab_id, current, state="unknown", reason="heartbeat_missing")
        if observed is None:
            return _base_status(lab_id, current, state="unknown", reason="heartbeat_invalid")
        return {
            **_base_status(lab_id, current, state="unknown", reason="heartbeat_stale"),
            "observedAt": _iso(observed),
            "ageSeconds": age_seconds,
        }

    assert observed is not None
    assert age_seconds is not None
    local_mode = _heartbeat_flag(heartbeat, "localMode", "localModeEnabled")
    session = session_projection(heartbeat)
    if not session["known"]:
        result = {
            **_base_status(
                lab_id,
                current,
                state="unknown",
                reason=session["reason"],
            ),
            "observedAt": _iso(observed),
            "ageSeconds": age_seconds,
        }
        result["capabilities"] = {
            "physicalLab": dict(result),
            "fmu": dict(result),
        }
        return result

    if local_mode or session["active"]:
        result = {
            **_base_status(
                lab_id,
                current,
                state="busy",
                reason="local_mode_enabled" if local_mode else session["reason"],
            ),
            "severity": "critical" if local_mode else "warning",
            "observedAt": _iso(observed),
            "ageSeconds": age_seconds,
        }
        result.update({
            "capabilities": {
                "physicalLab": dict(result),
                "fmu": dict(result),
            },
        })
        return result

    fallback_ready = heartbeat.get("ready") is True
    physical = _fresh_status(
        lab_id,
        observed,
        age_seconds,
        current,
        ready=_capability_ready(heartbeat, "physicalLab", fallback_ready),
    )
    fmu = _fresh_status(
        lab_id,
        observed,
        age_seconds,
        current,
        ready=_capability_ready(heartbeat, "fmu", fallback_ready),
        reason_ready="fmu_ready",
        reason_not_ready="fmu_not_ready",
    )
    physical["capabilities"] = {
        "physicalLab": physical.copy(),
        "fmu": fmu,
    }
    return physical


def project_fmu_runner_status(
    lab_id: Any,
    runner_status: Optional[Mapping[str, Any]],
    *,
    now: datetime,
) -> Dict[str, Any]:
    """Project a local FMU resource from the runner health signal."""
    current = _as_utc(now) or datetime.now(timezone.utc)
    return _project_fmu_runner_status(lab_id, runner_status, current)


def project_station_fmu_status(
    lab_id: Any,
    heartbeat: Optional[Mapping[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int,
    host_mapped: bool = True,
) -> Dict[str, Any]:
    """Project the FMU capability from a Lab Station heartbeat."""
    station_status = project_lab_status(
        lab_id,
        heartbeat,
        now=now,
        max_age_seconds=max_age_seconds,
        host_mapped=host_mapped,
    )
    capabilities = station_status.get("capabilities")
    fmu_status = capabilities.get("fmu") if isinstance(capabilities, Mapping) else None
    if not isinstance(fmu_status, Mapping):
        fmu_status = station_status
    result = dict(fmu_status)
    result["capabilities"] = {"fmu": dict(fmu_status)}
    return result


__all__ = [
    "heartbeat_is_fresh",
    "project_fmu_runner_status",
    "project_lab_status",
    "project_station_fmu_status",
]
