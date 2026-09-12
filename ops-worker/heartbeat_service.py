"""Heartbeat polling orchestration with explicit external dependencies."""

import json
from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional


def poll_heartbeat(
    host: Mapping[str, Any],
    include_events: bool = False,
    *,
    read_remote_file: Callable[..., str],
    persist_heartbeat: Callable[..., Any],
    db_engine: Any,
    sync_lab_to_basyx: Callable[..., Dict[str, Any]],
    logger: Any,
    default_heartbeat_path: str,
    default_events_path: str,
) -> Dict[str, Any]:
    """Read a Station heartbeat and perform best-effort side effects."""
    hb_path = host.get("heartbeat_path", default_heartbeat_path)
    events_path = host.get("events_path", default_events_path)
    content = read_remote_file(host, hb_path, None, None, None, None, None)
    heartbeat = json.loads(content)
    last_event: Optional[Dict[str, Any]] = None
    if include_events:
        try:
            tail = read_remote_file(host, events_path, None, None, None, None, None)
            if tail.strip():
                last_event = json.loads(tail.strip().splitlines()[-1])
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not read events for %s: %s", host.get("name"), exc)
    if db_engine:
        try:
            persist_heartbeat(db_engine, host, heartbeat, last_event)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("DB persistence failed for %s: %s", host.get("name"), exc)
    # Auto-sync AAS TechnicalData on heartbeat (best-effort, never blocks the poll)
    for lab_id in host.get("labs", []):
        try:
            sync_result = sync_lab_to_basyx(str(lab_id), host, heartbeat)
            if sync_result.get("disabled"):
                break  # AAS not configured on this gateway - skip remaining labs silently
            if sync_result.get("error"):
                logger.warning("AAS auto-sync failed for lab %s: %s", lab_id, sync_result["error"])
            else:
                logger.debug("AAS auto-synced for lab %s", lab_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("AAS auto-sync exception for lab %s: %s", lab_id, exc)
    return {"heartbeat": heartbeat, "last_event": last_event}
