"""Composition adapter for demo readiness and lifecycle operations."""

from collections.abc import Mapping
from typing import Any, Dict, Optional, Tuple


class DemoRuntime:
    """Resolve demo lifecycle dependencies from a live worker namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def get_mandatory_field(self, payload: Dict[str, Any], *keys: str) -> Optional[str]:
        return self._get("_get_mandatory_field_impl")(payload, *keys)

    def canonical_demo_lab_id(self, value: Any) -> Optional[str]:
        return self._get("_canonical_demo_lab_id_impl")(value)

    def demo_readiness(self) -> Dict[str, Any]:
        get = self._get
        return get("_build_demo_readiness_impl")(
            demo_lab_id=get("DEMO_LAB_ID"),
            demo_connection_id=get("DEMO_CONNECTION_ID"),
            demo_user=get("DEMO_USER"),
            max_age_seconds=get("DEMO_HEARTBEAT_MAX_AGE_SECONDS"),
            guacamole_db_engine=get("GUACAMOLE_DB_ENGINE"),
            db_engine=get("DB_ENGINE"),
            find_host_by_lab=get("HOSTS").get_by_lab,
            fetch_latest_heartbeat=get("_fetch_latest_heartbeat"),
            to_utc=get("to_utc"),
            sql_text=get("text"),
            now=lambda: get("datetime").now(get("timezone").utc),
            logger=get("logging"),
        )

    def demo_context(
        self,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        get = self._get
        return get("_build_demo_context_impl")(
            payload,
            operation_id_pattern=get("DEMO_OPERATION_ID_RE"),
            canonical_lab_id=get("_canonical_demo_lab_id"),
            configured_lab_id=get("DEMO_LAB_ID"),
            find_host_by_lab=get("HOSTS").get_by_lab,
            db_engine=get("DB_ENGINE"),
        )

    def operation_completed(self, demo_id: str, action: str) -> bool:
        get = self._get
        return get("_demo_operation_completed_impl")(
            demo_id,
            action,
            db_engine=get("DB_ENGINE"),
            sql_text=get("text"),
            logger=get("logging"),
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
        get = self._get
        return get("_record_demo_event_impl")(
            context,
            event,
            success,
            event_actions=get("DEMO_EVENT_ACTIONS"),
            record_operation=get("record_reservation_operation"),
            payload=payload,
            message=message,
        )

    def host_is_ready(self, host: Dict[str, Any]) -> bool:
        get = self._get
        return get("_demo_host_is_ready_impl")(
            host,
            db_engine=get("DB_ENGINE"),
            fetch_latest_heartbeat=get("_fetch_latest_heartbeat"),
            to_utc=get("to_utc"),
            max_age_seconds=get("DEMO_HEARTBEAT_MAX_AGE_SECONDS"),
            now=lambda: get("datetime").now(get("timezone").utc),
            logger=get("logging"),
        )

    def handle_demo_start(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        get = self._get
        return get("_handle_demo_start_impl")(
            payload,
            get_context=get("_demo_context"),
            operation_completed=get("_demo_operation_completed"),
            parse_bool=get("parse_bool"),
            host_is_ready=get("_demo_host_is_ready"),
            reservation_start=lambda value: get("handle_reservation_start")(value),
            reservation_end=lambda value: get("handle_reservation_end")(value),
            record_event=lambda *args, **kwargs: get("_record_demo_event")(
                *args,
                **kwargs,
            ),
        )

    def handle_demo_event(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        get = self._get
        return get("_handle_demo_event_impl")(
            payload,
            get_context=get("_demo_context"),
            operation_completed=get("_demo_operation_completed"),
            record_event=lambda *args, **kwargs: get("_record_demo_event")(
                *args,
                **kwargs,
            ),
            event_actions=get("DEMO_EVENT_ACTIONS"),
        )

    def handle_demo_end(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        get = self._get
        return get("_handle_demo_end_impl")(
            payload,
            get_context=get("_demo_context"),
            operation_completed=get("_demo_operation_completed"),
            reservation_end=lambda value: get("handle_reservation_end")(value),
            record_event=lambda *args, **kwargs: get("_record_demo_event")(
                *args,
                **kwargs,
            ),
        )


def create_demo_runtime(providers: Mapping[str, Any]) -> DemoRuntime:
    """Create a demo adapter bound to live worker providers."""
    return DemoRuntime(providers)


__all__ = ["DemoRuntime", "create_demo_runtime"]
