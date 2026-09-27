"""Persistence helpers for bounded Wake-on-LAN status evidence."""

from collections.abc import Mapping, Sequence
from typing import Any, Dict


def fetch_latest_wake_operations(
    connection: Any,
    lab_ids: Sequence[str],
    *,
    sql_text: Any,
) -> Dict[str, Dict[str, Any]]:
    """Return the newest persisted wake operation for each requested lab.

    Only the fields needed by the public projection are selected.  The caller
    is responsible for applying the evidence freshness window; an old success
    must never be treated as a current wake guarantee.
    """
    normalized_ids = []
    seen = set()
    for lab_id in lab_ids:
        key = str(lab_id or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized_ids.append(key)
    if connection is None or not normalized_ids:
        return {}

    placeholders = []
    params: Dict[str, Any] = {"wake_action": "wake"}
    for index, lab_id in enumerate(normalized_ids):
        name = f"lab_id_{index}"
        placeholders.append(f":{name}")
        params[name] = lab_id

    rows = connection.execute(
        sql_text(
            "SELECT lab_id, status, success, created_at "
            "FROM reservation_operations "
            "WHERE action = :wake_action AND lab_id IN ("
            + ", ".join(placeholders)
            + ") ORDER BY created_at DESC, id DESC"
        ),
        params,
    ).mappings().all()

    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lab_id = str(row.get("lab_id") or "").strip()
        if lab_id and lab_id not in latest:
            latest[lab_id] = {
                "status": row.get("status"),
                "success": bool(row.get("success")),
                "created_at": row.get("created_at"),
            }
    return latest


__all__ = ["fetch_latest_wake_operations"]
