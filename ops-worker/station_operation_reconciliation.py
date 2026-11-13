"""Shared Gateway sequence for dispatching durable Station operations."""

from collections.abc import Callable, Mapping
from typing import Any, Dict, Optional

from station_errors import StationUnreachable


def execute_with_operation_reconciliation(
    *,
    read_status: Callable[[], Optional[Mapping[str, Any]]],
    dispatch: Callable[[], Dict[str, Any]],
    normalize_stored: Callable[[Mapping[str, Any]], Dict[str, Any]],
    classify_uncertain: Callable[[Exception], Optional[StationUnreachable]],
) -> Dict[str, Any]:
    """Read by operation ID before dispatch and reconcile only uncertain outcomes.

    The callback owns the durable operation ID. This function never retries the
    mutating command: after an uncertain dispatch it reads the stored result and
    returns it, or preserves the original uncertainty if recovery is unavailable.
    """
    previous = read_status()
    if previous is not None:
        return normalize_stored(previous)

    try:
        return dispatch()
    except Exception as original_error:
        uncertain_error = classify_uncertain(original_error)
        if uncertain_error is None:
            raise
        try:
            previous = read_status()
        except Exception:
            raise uncertain_error from original_error
        if previous is None:
            raise uncertain_error from original_error
        return normalize_stored(previous)
