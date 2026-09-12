"""Pure request and notification input normalization helpers."""

from typing import Any, List, Optional


def parse_bool(value: Any, default: bool) -> bool:
    """Normalize common boolean representations while preserving defaults."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off")
    return bool(value)


def normalize_args(args: Any, default: Optional[List[str]] = None) -> List[str]:
    """Normalize command arguments into a fresh list of strings."""
    if args is None:
        return list(default or [])
    if isinstance(args, list):
        return [str(item) for item in args]
    return [str(args)]


def parse_recipients(value: Any, default: Optional[List[str]] = None) -> List[str]:
    """Normalize comma-separated recipient values while preserving order."""
    if value is None:
        return list(default or [])
    if isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    recipients: List[str] = []
    for item in items:
        for part in item.split(","):
            normalized = part.strip()
            if normalized:
                recipients.append(normalized)
    return recipients
