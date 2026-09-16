"""Composition adapter for heartbeat polling, persistence and SSE."""

from typing import Any, Dict, Optional

from datetime_values import to_utc as _to_utc
from heartbeat_context import HeartbeatContext
from heartbeat_persistence import (
    load_persisted_heartbeat as _load_persisted_heartbeat,
    persist_heartbeat as _persist_heartbeat,
)
from heartbeat_poller import poll_all_hosts as _poll_all_hosts
from heartbeat_service import poll_heartbeat as _poll_heartbeat
from heartbeat_stream import (
    format_sse_event as _format_sse_event,
    generate_heartbeat_stream as _generate_heartbeat_stream,
)


class HeartbeatRuntime:
    """Coordinate heartbeat operations from explicit dependencies."""

    def __init__(self, context: HeartbeatContext):
        self._context = context

    def to_utc(self, value: Any) -> Optional[Any]:
        context = self._context
        return _to_utc(
            value,
            parse_datetime=context.parse_datetime,
            utc_timezone=context.utc_timezone,
        )

    def persist_heartbeat(
        self,
        engine: Any,
        host: Dict[str, Any],
        heartbeat: Dict[str, Any],
        last_event: Optional[Dict[str, Any]],
    ) -> None:
        context = self._context
        return _persist_heartbeat(
            engine,
            host,
            heartbeat,
            last_event,
            to_utc=self.to_utc,
            now=context.now,
            sql_text=context.sql_text,
            json_dumps=context.json_dumps,
        )

    def poll_heartbeat(
        self,
        host: Dict[str, Any],
        include_events: bool = False,
    ) -> Dict[str, Any]:
        context = self._context
        return _poll_heartbeat(
            host,
            include_events,
            read_remote_file=context.read_remote_file,
            persist_heartbeat=context.get_persist_heartbeat,
            db_engine=context.get_db_engine(),
            sync_lab_to_basyx=context.sync_lab_to_basyx,
            resolve_lab_ids_for_host=context.resolve_lab_ids_for_host,
            logger=context.get_logger(),
            default_heartbeat_path=context.default_heartbeat_path,
            default_events_path=context.default_events_path,
        )

    def format_sse_event(self, event: str, data: str) -> str:
        return _format_sse_event(event, data)

    def generate_heartbeat_stream(self, host: Dict[str, Any], include_events: bool):
        context = self._context
        return _generate_heartbeat_stream(
            host,
            include_events,
            poll_heartbeat=context.get_poll_heartbeat,
            format_sse_event=_format_sse_event,
            trust_error_type=context.trust_error_type,
            missing_credentials_predicate=context.missing_credentials_predicate,
            trust_error_payload=context.trust_error_payload,
            request_id=context.request_id,
            logger=context.get_logger(),
            sanitize_log_value=context.sanitize_log_value,
            credentials_required_message=context.credentials_required_message,
            heartbeat_interval_seconds=context.heartbeat_interval_seconds,
            sleep=context.sleep,
        )

    def poll_all_hosts(self) -> Any:
        context = self._context
        return _poll_all_hosts(
            context.get_host_registry(),
            context.get_poll_heartbeat,
            context.get_logger(),
        )

    def load_persisted_heartbeat(
        self,
        lab_id: str,
        host: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        context = self._context
        return _load_persisted_heartbeat(
            context.get_db_engine(),
            lab_id,
            host,
            fetch_latest_heartbeat=context.fetch_latest_heartbeat,
        )


def create_heartbeat_runtime(context: HeartbeatContext) -> HeartbeatRuntime:
    """Create a heartbeat runtime bound to explicit dependencies."""
    return HeartbeatRuntime(context)


__all__ = ["HeartbeatRuntime", "create_heartbeat_runtime"]
