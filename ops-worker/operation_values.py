"""Pure projections for persisted reservation operations."""

import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence


def rows_to_operations(
    rows: Sequence[Mapping[str, Any]],
    *,
    to_iso: Callable[[Any], Optional[str]],
) -> List[Dict[str, Any]]:
    """Project storage rows into the public operation representation."""
    op_entries: List[Dict[str, Any]] = []
    for op in rows:
        payload = op.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                # Optional operation payloads may contain opaque non-JSON values.
                pass
        op_entries.append(
            {
                "action": op.get("action"),
                "status": op.get("status"),
                "success": bool(op.get("success")),
                "message": op.get("message"),
                "payload": payload,
                "responseCode": op.get("response_code"),
                "durationMs": op.get("duration_ms"),
                "createdAt": to_iso(op.get("created_at")),
            }
        )
    return op_entries


__all__ = ["rows_to_operations"]
