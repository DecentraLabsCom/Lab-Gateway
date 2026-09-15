"""Composition adapter for reservation timeline helpers."""

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from timeline_context import TimelineContext


class TimelineRuntime:
    """Expose timeline formatting and query helpers through explicit ports."""

    def __init__(self, context: TimelineContext):
        self._context = context

    def to_iso(self, value: Any) -> Optional[str]:
        return self._context.to_iso_impl(
            value,
            parse_datetime=self._context.get_datetime().fromisoformat,
            utc_timezone=self._context.get_timezone().utc,
        )

    def sanitize_limit(self, value: Optional[str]) -> int:
        return self._context.sanitize_limit_impl(
            value,
            default_limit=self._context.get_default_limit(),
            max_limit=self._context.get_max_limit(),
        )

    def sanitize_offset(self, value: Optional[str]) -> int:
        return self._context.sanitize_offset_impl(value)

    def rows_to_operations(self, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return self._context.rows_to_operations_impl(
            rows,
            to_iso=self._context.get_to_iso(),
        )

    def build_reservation_timeline(
        self,
        reservation_id: str,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        return self._context.build_reservation_timeline_impl(
            reservation_id,
            limit,
            offset,
            engine=self._context.get_db_engine(),
            host_by_lab=self._context.get_host_by_lab(),
            sql_text=self._context.get_sql_text(),
            rows_to_operations=self._context.get_rows_to_operations(),
            to_iso=self._context.get_to_iso(),
            phase_lookback=self._context.get_phase_lookback(),
            fetch_latest_heartbeat=self._context.get_fetch_latest_heartbeat(),
            summarize_phases=self._context.get_summarize_phases(),
        )

    def fetch_latest_heartbeat(self, conn: Any, host_name: str) -> Optional[Dict[str, Any]]:
        return self._context.fetch_latest_heartbeat_impl(
            conn,
            host_name,
            sql_text=self._context.get_sql_text(),
            json_loads=self._context.get_json_loads(),
            to_iso=self._context.get_to_iso(),
        )

    def summarize_phases(self, operations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._context.summarize_phases_impl(operations)


def create_timeline_runtime(context: TimelineContext) -> TimelineRuntime:
    """Create a timeline adapter bound to explicit ports."""
    return TimelineRuntime(context)


__all__ = ["TimelineRuntime", "create_timeline_runtime"]
