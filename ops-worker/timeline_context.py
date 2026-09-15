"""Explicit dependencies for reservation timeline projections."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TimelineContext:
    """Timeline implementations and database, registry and serialization ports."""

    to_iso_impl: Callable[..., Optional[str]]
    get_datetime: Callable[[], Any]
    get_timezone: Callable[[], Any]
    sanitize_limit_impl: Callable[..., int]
    get_default_limit: Callable[[], int]
    get_max_limit: Callable[[], int]
    sanitize_offset_impl: Callable[[Optional[str]], int]
    rows_to_operations_impl: Callable[..., List[Dict[str, Any]]]
    get_to_iso: Callable[[], Callable[[Any], Optional[str]]]
    build_reservation_timeline_impl: Callable[..., Dict[str, Any]]
    get_db_engine: Callable[[], Any]
    get_host_by_lab: Callable[[], Callable[[Any], Optional[Mapping[str, Any]]]]
    get_sql_text: Callable[[], Callable[[str], Any]]
    get_rows_to_operations: Callable[[], Callable[[Sequence[Mapping[str, Any]]], List[Dict[str, Any]]]]
    get_phase_lookback: Callable[[], int]
    get_fetch_latest_heartbeat: Callable[[], Callable[[Any, str], Optional[Dict[str, Any]]]]
    get_summarize_phases: Callable[[], Callable[[Sequence[Mapping[str, Any]]], Dict[str, Any]]]
    fetch_latest_heartbeat_impl: Callable[..., Optional[Dict[str, Any]]]
    get_json_loads: Callable[[], Callable[[str], Any]]
    summarize_phases_impl: Callable[[Sequence[Mapping[str, Any]]], Dict[str, Any]]


__all__ = ["TimelineContext"]
