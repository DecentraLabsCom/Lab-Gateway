"""Composition adapter for demo readiness and lifecycle operations."""

from typing import Any, Dict, Optional, Tuple

from demo_context import DemoContext


class DemoRuntime:
    """Expose demo lifecycle operations through explicit dependency ports."""

    def __init__(self, context: DemoContext):
        self._context = context

    def get_mandatory_field(self, payload: Dict[str, Any], *keys: str) -> Optional[str]:
        return self._context.get_mandatory_field_impl(payload, *keys)

    def canonical_demo_lab_id(self, value: Any) -> Optional[str]:
        return self._context.canonical_demo_lab_id_impl(value)

    def demo_readiness(self) -> Dict[str, Any]:
        return self._context.build_demo_readiness_impl(
            demo_lab_id=self._context.get_demo_lab_id(),
            demo_connection_id=self._context.get_demo_connection_id(),
            demo_user=self._context.get_demo_user(),
            max_age_seconds=self._context.get_demo_heartbeat_max_age(),
            guacamole_db_engine=self._context.get_guacamole_db_engine(),
            db_engine=self._context.get_db_engine(),
            find_host_by_lab=self._context.get_find_host_by_lab(),
            fetch_latest_heartbeat=self._context.get_fetch_latest_heartbeat(),
            to_utc=self._context.get_to_utc(),
            sql_text=self._context.get_sql_text(),
            now=self._context.get_now(),
            logger=self._context.get_logger(),
        )

    def demo_context(
        self,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return self._context.build_demo_context_impl(
            payload,
            operation_id_pattern=self._context.get_demo_operation_id_pattern(),
            canonical_lab_id=self._context.get_canonical_demo_lab_id(),
            configured_lab_id=self._context.get_demo_lab_id(),
            find_host_by_lab=self._context.get_find_host_by_lab(),
            db_engine=self._context.get_db_engine(),
        )

    def operation_completed(self, demo_id: str, action: str) -> bool:
        return self._context.operation_completed_impl(
            demo_id,
            action,
            db_engine=self._context.get_db_engine(),
            sql_text=self._context.get_sql_text(),
            logger=self._context.get_logger(),
        )

    def record_demo_event(
        self,
        context: Dict[str, Any],
        event: str,
        success: bool,
        *,
        payload: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        return self._context.record_demo_event_impl(
            context,
            event,
            success,
            event_actions=self._context.get_demo_event_actions(),
            record_operation=self._context.get_record_reservation_operation(),
            payload=payload,
            message=message,
        )

    def host_is_ready(self, host: Dict[str, Any]) -> bool:
        return self._context.demo_host_is_ready_impl(
            host,
            db_engine=self._context.get_db_engine(),
            fetch_latest_heartbeat=self._context.get_fetch_latest_heartbeat(),
            to_utc=self._context.get_to_utc(),
            max_age_seconds=self._context.get_demo_heartbeat_max_age(),
            now=self._context.get_now(),
            logger=self._context.get_logger(),
        )

    def handle_demo_start(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        return self._context.handle_demo_start_impl(
            payload,
            get_context=self._context.get_demo_context(),
            operation_completed=self._context.get_operation_completed(),
            parse_bool=self._context.get_parse_bool(),
            host_is_ready=self._context.get_demo_host_is_ready(),
            reservation_start=self._context.get_reservation_start(),
            reservation_end=self._context.get_reservation_end(),
            record_event=self._context.get_record_demo_event(),
        )

    def handle_demo_event(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        return self._context.handle_demo_event_impl(
            payload,
            get_context=self._context.get_demo_context(),
            operation_completed=self._context.get_operation_completed(),
            record_event=self._context.get_record_demo_event(),
            event_actions=self._context.get_demo_event_actions(),
        )

    def handle_demo_end(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        return self._context.handle_demo_end_impl(
            payload,
            get_context=self._context.get_demo_context(),
            operation_completed=self._context.get_operation_completed(),
            reservation_end=self._context.get_reservation_end(),
            record_event=self._context.get_record_demo_event(),
        )


def create_demo_runtime(context: DemoContext) -> DemoRuntime:
    """Create a demo adapter bound to explicit ports."""
    return DemoRuntime(context)


__all__ = ["DemoRuntime", "create_demo_runtime"]
