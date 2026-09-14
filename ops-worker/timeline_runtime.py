"""Composition adapter for reservation timeline helpers."""

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional


class TimelineRuntime:
    """Resolve timeline formatting and query helpers from live providers."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def to_iso(self, value: Any) -> Optional[str]:
        get = self._get
        return get("_to_iso_impl")(
            value,
            parse_datetime=get("datetime").fromisoformat,
            utc_timezone=get("timezone").utc,
        )

    def sanitize_limit(self, value: Optional[str]) -> int:
        get = self._get
        return get("_sanitize_limit_impl")(
            value,
            default_limit=get("TIMELINE_DEFAULT_LIMIT"),
            max_limit=get("TIMELINE_MAX_LIMIT"),
        )

    def sanitize_offset(self, value: Optional[str]) -> int:
        return self._get("_sanitize_offset_impl")(value)

    def rows_to_operations(self, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return self._get("_rows_to_operations_impl")(
            rows,
            to_iso=self._get("_to_iso"),
        )

    def build_reservation_timeline(
        self,
        reservation_id: str,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_build_reservation_timeline_impl")(
            reservation_id,
            limit,
            offset,
            engine=get("DB_ENGINE"),
            host_by_lab=get("HOSTS").get_by_lab,
            sql_text=get("text"),
            rows_to_operations=get("_rows_to_operations"),
            to_iso=get("_to_iso"),
            phase_lookback=get("TIMELINE_PHASE_LOOKBACK"),
            fetch_latest_heartbeat=get("_fetch_latest_heartbeat"),
            summarize_phases=get("_summarize_phases"),
        )

    def fetch_latest_heartbeat(self, conn: Any, host_name: str) -> Optional[Dict[str, Any]]:
        get = self._get
        return get("_fetch_latest_heartbeat_impl")(
            conn,
            host_name,
            sql_text=get("text"),
            json_loads=get("json").loads,
            to_iso=get("_to_iso"),
        )

    def summarize_phases(self, operations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._get("_summarize_phases_impl")(operations)


def create_timeline_runtime(providers: Mapping[str, Any]) -> TimelineRuntime:
    """Create a timeline adapter bound to live providers."""
    return TimelineRuntime(providers)


__all__ = ["TimelineRuntime", "create_timeline_runtime"]
