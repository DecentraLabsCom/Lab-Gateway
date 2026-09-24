"""Request parsing and response handling for the public lab-status projection."""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from lab_status_service import heartbeat_is_fresh, project_lab_status


MAX_PUBLIC_STATUS_LABS = 50


def parse_lab_ids(values: Iterable[str]) -> List[str]:
    """Normalize repeated/comma-separated numeric lab ids with a hard bound."""
    result: List[str] = []
    seen = set()
    for value in values:
        for candidate in str(value or "").split(","):
            candidate = candidate.strip()
            if not candidate:
                continue
            if not candidate.isdigit() or len(candidate) > 20:
                raise ValueError("labIds must contain non-negative numeric ids")
            normalized = str(int(candidate))
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
            if len(result) > MAX_PUBLIC_STATUS_LABS:
                raise ValueError(f"A maximum of {MAX_PUBLIC_STATUS_LABS} lab ids is allowed")
    if not result:
        raise ValueError("At least one lab id is required")
    return result


def build_public_lab_status_response(
    lab_ids: Sequence[str],
    *,
    engine: Any,
    resolve_lab_associations: Callable[[], Sequence[dict]],
    resolve_lab_status_targets: Callable[[], Sequence[dict]],
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]],
    probe_lab_targets: Callable[[Sequence[dict]], Dict[str, Dict[str, Any]]],
    now: Callable[[], datetime],
    max_age_seconds: int,
) -> Dict[str, Any]:
    current = now()
    statuses = []
    connection = None
    try:
        if engine:
            connection = engine.connect()
        associations = resolve_lab_associations() or []
        host_by_lab = {
            str(entry.get("labId")): str(entry.get("hostName") or "").strip()
            for entry in associations
            if isinstance(entry, dict)
        }
        targets_by_lab = {
            str(entry.get("labId")): entry
            for entry in (resolve_lab_status_targets() or [])
            if isinstance(entry, dict) and str(entry.get("labId") or "").strip()
        }
        heartbeats = {}
        for lab_id in lab_ids:
            host_name = host_by_lab.get(str(lab_id), "")
            heartbeat = None
            if host_name and connection is not None:
                heartbeat = fetch_latest_heartbeat(connection, host_name)
            heartbeats[str(lab_id)] = heartbeat

        targets_to_probe = [
            targets_by_lab[str(lab_id)]
            for lab_id in lab_ids
            if str(lab_id) in targets_by_lab
            and not heartbeat_is_fresh(
                heartbeats[str(lab_id)],
                now=current,
                max_age_seconds=max_age_seconds,
            )
        ]
        probes = probe_lab_targets(targets_to_probe) if targets_to_probe else {}

        for lab_id in lab_ids:
            host_name = host_by_lab.get(str(lab_id), "")
            statuses.append(project_lab_status(
                lab_id,
                heartbeats[str(lab_id)],
                now=current,
                max_age_seconds=max_age_seconds,
                host_mapped=bool(host_name),
                target_probe=probes.get(str(lab_id)),
            ))
    finally:
        if connection is not None:
            connection.close()
    return {
        "generatedAt": current.isoformat().replace("+00:00", "Z"),
        "maxAgeSeconds": int(max_age_seconds),
        "statuses": statuses,
    }


__all__ = ["MAX_PUBLIC_STATUS_LABS", "build_public_lab_status_response", "parse_lab_ids"]
