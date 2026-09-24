"""Request parsing and response handling for the public lab-status projection."""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from lab_status_service import (
    heartbeat_is_fresh,
    project_fmu_runner_status,
    project_lab_status,
    project_station_fmu_status,
)


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
    resolve_lab_resources: Optional[Callable[[], Sequence[dict]]] = None,
    resolve_fmu_station_host: Optional[Callable[[], str]] = None,
    fetch_fmu_runner_status: Optional[Callable[[], Optional[Mapping[str, Any]]]] = None,
) -> Dict[str, Any]:
    current = now()
    statuses = []
    connection = None
    try:
        resources_by_lab = {
            str(entry.get("labId")): dict(entry)
            for entry in (resolve_lab_resources() if resolve_lab_resources else []) or []
            if isinstance(entry, dict) and str(entry.get("labId") or "").strip()
        }

        def resource_type(lab_id: str) -> str:
            return str(resources_by_lab.get(lab_id, {}).get("resourceType") or "").strip().lower()

        def fmu_backend(lab_id: str) -> str:
            backend = str(
                resources_by_lab.get(lab_id, {}).get("executionBackend") or "station"
            ).strip().lower()
            return "local" if backend in {"local", "gateway", "gateway-local", "gateway_local"} else "station"

        def requires_station_data(lab_id: str) -> bool:
            return not (
                resource_type(lab_id) == "fmu"
                and fmu_backend(lab_id) == "local"
            )

        needs_station_data = any(requires_station_data(str(lab_id)) for lab_id in lab_ids)
        if needs_station_data:
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
        else:
            host_by_lab = {}
            targets_by_lab = {}

        fmu_station_host = ""
        if resolve_fmu_station_host and any(
            resource_type(str(lab_id)) == "fmu"
            and fmu_backend(str(lab_id)) == "station"
            for lab_id in lab_ids
        ):
            fmu_station_host = str(resolve_fmu_station_host() or "").strip()

        def fmu_host(lab_id: str) -> str:
            return str(
                resources_by_lab.get(lab_id, {}).get("stationHostName") or fmu_station_host
            ).strip()

        heartbeats = {}
        for lab_id in lab_ids:
            lab_key = str(lab_id)
            if resource_type(lab_key) == "fmu" and fmu_backend(lab_key) == "local":
                heartbeats[str(lab_id)] = None
                continue
            host_name = (
                fmu_host(lab_key)
                if resource_type(lab_key) == "fmu"
                else host_by_lab.get(lab_key, "")
            )
            heartbeat = None
            if host_name and connection is not None:
                heartbeat = fetch_latest_heartbeat(connection, host_name)
            heartbeats[str(lab_id)] = heartbeat

        targets_to_probe = [
            targets_by_lab[str(lab_id)]
            for lab_id in lab_ids
            if str(lab_id) in targets_by_lab
            and resource_type(str(lab_id)) != "fmu"
            and not heartbeat_is_fresh(
                heartbeats[str(lab_id)],
                now=current,
                max_age_seconds=max_age_seconds,
            )
        ]
        probes = probe_lab_targets(targets_to_probe) if targets_to_probe else {}
        fmu_runner_status = None
        if (
            fetch_fmu_runner_status
            and any(
                resource_type(str(lab_id)) == "fmu"
                and (
                    fmu_backend(str(lab_id)) == "local"
                    or not fmu_host(str(lab_id))
                )
                for lab_id in lab_ids
            )
        ):
            fmu_runner_status = fetch_fmu_runner_status()

        for lab_id in lab_ids:
            lab_key = str(lab_id)
            if resource_type(lab_key) == "fmu":
                if fmu_backend(lab_key) == "local" or not fmu_host(lab_key):
                    statuses.append(project_fmu_runner_status(
                        lab_id,
                        fmu_runner_status,
                        now=current,
                    ))
                else:
                    statuses.append(project_station_fmu_status(
                        lab_id,
                        heartbeats[lab_key],
                        now=current,
                        max_age_seconds=max_age_seconds,
                        host_mapped=True,
                    ))
                continue
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
