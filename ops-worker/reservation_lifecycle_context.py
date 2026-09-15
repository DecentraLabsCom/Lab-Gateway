"""Explicit dependencies for reservation lifecycle operations."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ReservationLifecycleContext:
    """Host lookup, parsing and operational step ports for reservation start/end."""

    handle_reservation_start_impl: Callable[..., Tuple[Dict[str, Any], int]]
    handle_reservation_end_impl: Callable[..., Tuple[Dict[str, Any], int]]
    get_hosts: Callable[[], Any]
    get_mandatory_field: Callable[[], Callable[..., Optional[str]]]
    get_parse_bool: Callable[[], Callable[[Any, bool], bool]]
    get_execute_power_phase: Callable[
        [], Callable[[str, Optional[str], Mapping[str, Any], str, Dict[str, Any]], Dict[str, Any]]
    ]
    get_perform_wake_step: Callable[
        [], Callable[[Mapping[str, Any], str, Optional[str], Dict[str, Any]], Tuple[bool, Dict[str, Any]]]
    ]
    get_perform_command_step: Callable[
        [], Callable[..., Tuple[bool, Dict[str, Any]]]
    ]
    get_normalize_args: Callable[
        [], Callable[[Any, Optional[List[str]]], List[str]]
    ]


__all__ = ["ReservationLifecycleContext"]
