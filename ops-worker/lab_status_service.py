"""Pure projection of the last Lab Station heartbeat into a public status."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from heartbeat_readiness import capability_ready
from wake_ops_service import WAKE_EVIDENCE_MAX_AGE_SECONDS


DEFAULT_WAKE_EVIDENCE_MAX_AGE_SECONDS = WAKE_EVIDENCE_MAX_AGE_SECONDS


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


def _status_access(state: str) -> str:
    if state in {"ready", "reachable"}:
        return "ready"
    if state == "busy":
        return "busy"
    if state == "not_ready":
        return "inaccessible"
    return "unknown"


def project_wake_status(
    wake_status: Optional[Mapping[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int = DEFAULT_WAKE_EVIDENCE_MAX_AGE_SECONDS,
) -> Dict[str, Any]:
    """Project host configuration and recent real wake evidence separately."""
    current = _as_utc(now) or datetime.now(timezone.utc)
    configured = bool(
        isinstance(wake_status, Mapping)
        and wake_status.get("configured") is True
    )
    configuration_known = bool(
        isinstance(wake_status, Mapping)
        and wake_status.get("configurationKnown") is True
    )
    operation = wake_status.get("operation") if isinstance(wake_status, Mapping) else None
    observed = None
    age_seconds = None
    state = "unknown"
    source = "status_unavailable"

    if isinstance(operation, Mapping):
        observed = _as_utc(operation.get("created_at") or operation.get("createdAt"))
        if observed is not None:
            age_seconds = max(0, int((current - observed).total_seconds()))
        if (
            observed is not None
            and age_seconds is not None
            and age_seconds <= max(30, int(max_age_seconds))
        ):
            state = "verified" if bool(operation.get("success")) else "failed"
            source = "reservation_wake_operation"

    if state == "unknown" and configured:
        state = "configured"
        source = "host_configuration"
        observed = None
        age_seconds = None
    elif state == "unknown" and configuration_known:
        state = "failed"
        source = "host_configuration"
        observed = None
        age_seconds = None

    return {
        "state": state,
        "source": source,
        "observedAt": _iso(observed) if observed is not None else None,
        "ageSeconds": age_seconds,
    }


def _attach_operational_dimensions(
    result: Dict[str, Any],
    *,
    now: datetime,
    wake_status: Optional[Mapping[str, Any]] = None,
    include_wake: bool = True,
    wake_max_age_seconds: int = DEFAULT_WAKE_EVIDENCE_MAX_AGE_SECONDS,
) -> Dict[str, Any]:
    access = _status_access(str(result.get("state") or "unknown"))
    result["access"] = access
    wake = project_wake_status(
        wake_status,
        now=now,
        max_age_seconds=wake_max_age_seconds,
    ) if include_wake else None
    if include_wake:
        result["wake"] = wake

    if access == "ready":
        availability = "now"
    elif access == "busy":
        availability = "unavailable"
    elif wake and wake["state"] == "verified":
        availability = "on_demand"
    elif wake and wake["state"] == "configured":
        availability = "recoverable"
    elif wake and wake["state"] == "failed":
        availability = "unavailable"
    elif access == "inaccessible":
        availability = "unavailable"
    else:
        availability = "unknown"
    result["availability"] = availability
    return result


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
    station = heartbeat.get("station")
    if isinstance(station, Mapping):
        merged.update(station)
    return merged


def _nested_status(heartbeat: Mapping[str, Any]) -> Mapping[str, Any]:
    status = heartbeat.get("status")
    return status if isinstance(status, Mapping) else {}


def _heartbeat_flag(heartbeat: Mapping[str, Any], top_level: str, nested: str) -> bool:
    if heartbeat.get(top_level) is True:
        return True
    if nested in heartbeat and isinstance(heartbeat.get(nested), bool):
        return heartbeat.get(nested) is True
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

    raw_active = sessions.get("active")
    if isinstance(raw_active, list):
        active = any(
            isinstance(entry, Mapping)
            and entry.get("active") is not False
            and entry.get("kind") not in {"management", "service"}
            for entry in raw_active
        )
    elif isinstance(raw_active, bool):
        active = raw_active
    else:
        active = legacy_local_session
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
    return _attach_operational_dimensions(result, now=current, include_wake=False)


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
    elif signal == "busy":
        state = "busy"
        severity = "warning"
    elif signal == "not_ready":
        state = "not_ready"
        severity = "critical"
    else:
        state = "unknown"
        severity = "neutral"
    reason = str(status.get("reason") or "fmu_runner_unavailable").strip()
    if reason not in {
        "fmu_ready",
        "fmu_capacity_exhausted",
        "fmu_not_ready",
        "fmu_runner_unavailable",
    }:
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
        "resourceType": "fmu",
    }
    observed = _as_utc(status.get("observedAt"))
    age_seconds = None
    if observed is not None:
        age_seconds = max(0, int((current - observed).total_seconds()))
        result.update({
            "observedAt": _iso(observed),
            "ageSeconds": age_seconds,
        })
    _attach_operational_dimensions(result, now=current, include_wake=False)
    executor_state = (
        "ready"
        if signal in {"ready", "busy"}
        else "not_ready"
        if signal == "not_ready"
        else "unknown"
    )
    result["executor"] = {
        "state": executor_state,
        "source": "fmu_runner_health",
        "observedAt": result.get("observedAt"),
        "ageSeconds": age_seconds,
    }
    raw_capacity = status.get("capacity")
    capacity = raw_capacity if isinstance(raw_capacity, Mapping) else {}
    capacity_state = str(capacity.get("state") or "unknown").strip().lower()
    if capacity_state not in {"available", "busy", "unknown"}:
        capacity_state = "unknown"
    result["capacity"] = {
        "state": capacity_state,
        "active": capacity.get("active") if isinstance(capacity.get("active"), int) else None,
        "maximum": capacity.get("maximum") if isinstance(capacity.get("maximum"), int) else None,
        "available": capacity.get("available") if isinstance(capacity.get("available"), int) else None,
        "source": "fmu_runner_health",
        "observedAt": result.get("observedAt"),
        "ageSeconds": age_seconds,
    }
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
    wake_status: Optional[Mapping[str, Any]] = None,
    wake_max_age_seconds: int = DEFAULT_WAKE_EVIDENCE_MAX_AGE_SECONDS,
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
            result = _project_target_probe(lab_id, target_probe, current)
        elif not host_mapped:
            result = _base_status(lab_id, current, state="unknown", reason="lab_not_mapped")
        else:
            result = _base_status(lab_id, current, state="unknown", reason="heartbeat_missing")
        return _attach_operational_dimensions(
            result,
            now=current,
            wake_status=wake_status,
            wake_max_age_seconds=wake_max_age_seconds,
        )
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
            result = _project_target_probe(lab_id, target_probe, current)
        elif not host_mapped:
            result = _base_status(lab_id, current, state="unknown", reason="lab_not_mapped")
        elif not heartbeat:
            result = _base_status(lab_id, current, state="unknown", reason="heartbeat_missing")
        elif observed is None:
            result = _base_status(lab_id, current, state="unknown", reason="heartbeat_invalid")
        else:
            result = {
                **_base_status(lab_id, current, state="unknown", reason="heartbeat_stale"),
                "observedAt": _iso(observed),
                "ageSeconds": age_seconds,
            }
        return _attach_operational_dimensions(
            result,
            now=current,
            wake_status=wake_status,
            wake_max_age_seconds=wake_max_age_seconds,
        )

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
        _attach_operational_dimensions(
            result,
            now=current,
            wake_status=wake_status,
            wake_max_age_seconds=wake_max_age_seconds,
        )
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
        _attach_operational_dimensions(
            result,
            now=current,
            wake_status=wake_status,
            wake_max_age_seconds=wake_max_age_seconds,
        )
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
    _attach_operational_dimensions(
        physical,
        now=current,
        wake_status=wake_status,
        wake_max_age_seconds=wake_max_age_seconds,
    )
    _attach_operational_dimensions(fmu, now=current, include_wake=False)
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


__all__ = [
    "DEFAULT_WAKE_EVIDENCE_MAX_AGE_SECONDS",
    "heartbeat_is_fresh",
    "project_fmu_runner_status",
    "project_lab_status",
    "project_wake_status",
]
