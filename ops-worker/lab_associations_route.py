"""Composition for the calculated lab-to-host association projection."""

from collections.abc import Callable, Sequence
from typing import Any, Mapping


def handle_lab_associations(
    *,
    resolve_lab_associations: Callable[[], Sequence[Mapping[str, Any]]],
    jsonify: Callable[[Any], Any],
) -> Any:
    """Return only the stable identifiers needed by Lab Manager selectors."""
    associations = []
    for association in resolve_lab_associations():
        if not isinstance(association, Mapping):
            continue
        lab_id = str(association.get("labId") or "").strip()
        host_name = str(association.get("hostName") or "").strip()
        if lab_id and host_name:
            associations.append({"labId": lab_id, "hostName": host_name})
    return jsonify({"associations": associations})


__all__ = ["handle_lab_associations"]
