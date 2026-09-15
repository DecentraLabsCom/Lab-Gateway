"""Explicit dependencies for demo readiness and lifecycle operations."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class DemoContext:
    """Readiness, persistence and lifecycle ports for demo operations."""

    get_mandatory_field_impl: Callable[..., Optional[str]]
    canonical_demo_lab_id_impl: Callable[[Any], Optional[str]]
    build_demo_readiness_impl: Callable[..., Dict[str, Any]]
    get_demo_lab_id: Callable[[], Optional[str]]
    get_demo_connection_id: Callable[[], Optional[str]]
    get_demo_user: Callable[[], Optional[str]]
    get_demo_heartbeat_max_age: Callable[[], int]
    get_guacamole_db_engine: Callable[[], Any]
    get_db_engine: Callable[[], Any]
    get_find_host_by_lab: Callable[[], Callable[..., Any]]
    get_fetch_latest_heartbeat: Callable[[], Callable[..., Any]]
    get_to_utc: Callable[[], Callable[..., Any]]
    get_sql_text: Callable[[], Callable[..., Any]]
    get_now: Callable[[], Callable[[], Any]]
    get_logger: Callable[[], Any]
    build_demo_context_impl: Callable[..., Tuple[Optional[Dict[str, Any]], Optional[str]]]
    get_demo_operation_id_pattern: Callable[[], Any]
    get_canonical_demo_lab_id: Callable[[], Callable[[Any], Optional[str]]]
    operation_completed_impl: Callable[..., bool]
    record_demo_event_impl: Callable[..., Any]
    get_demo_event_actions: Callable[[], Dict[str, str]]
    get_record_reservation_operation: Callable[[], Callable[..., Any]]
    demo_host_is_ready_impl: Callable[..., bool]
    handle_demo_start_impl: Callable[..., Tuple[Dict[str, Any], int]]
    get_demo_context: Callable[[], Callable[..., Any]]
    get_operation_completed: Callable[[], Callable[..., bool]]
    get_parse_bool: Callable[[], Callable[..., bool]]
    get_demo_host_is_ready: Callable[[], Callable[..., bool]]
    get_reservation_start: Callable[[], Callable[..., Any]]
    get_reservation_end: Callable[[], Callable[..., Any]]
    get_record_demo_event: Callable[[], Callable[..., Any]]
    handle_demo_event_impl: Callable[..., Tuple[Dict[str, Any], int]]
    handle_demo_end_impl: Callable[..., Tuple[Dict[str, Any], int]]


__all__ = ["DemoContext"]
