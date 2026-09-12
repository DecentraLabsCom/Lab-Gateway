"""Pure value helpers used by the demo and reservation handlers."""

from typing import Any, Dict, Optional


def get_mandatory_field(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    """Return the first non-empty value for the requested payload keys."""
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def canonical_demo_lab_id(value: Any) -> Optional[str]:
    """Normalize a demo lab identifier while rejecting non-decimal input."""
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    return str(int(raw))


__all__ = ["canonical_demo_lab_id", "get_mandatory_field"]
