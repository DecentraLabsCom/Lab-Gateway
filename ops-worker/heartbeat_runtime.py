"""Composition adapter for heartbeat polling, persistence and SSE."""

from collections.abc import Mapping
from typing import Any, Dict, Optional


class HeartbeatRuntime:
    """Resolve heartbeat operations from a live worker provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def to_utc(self, value: Any) -> Optional[Any]:
        get = self._get
        return get("_to_utc_impl")(
            value,
            parse_datetime=get("datetime").fromisoformat,
            utc_timezone=get("timezone").utc,
        )

    def persist_heartbeat(
        self,
        engine: Any,
        host: Dict[str, Any],
        heartbeat: Dict[str, Any],
        last_event: Optional[Dict[str, Any]],
    ) -> None:
        get = self._get
        return get("_persist_heartbeat_impl")(
            engine,
            host,
            heartbeat,
            last_event,
            to_utc=get("to_utc"),
            now=lambda: get("datetime").now(get("timezone").utc),
            sql_text=get("text"),
            json_dumps=get("json").dumps,
        )

    def poll_heartbeat(
        self,
        host: Dict[str, Any],
        include_events: bool = False,
    ) -> Dict[str, Any]:
        get = self._get
        return get("_poll_heartbeat_impl")(
            host,
            include_events,
            read_remote_file=get("read_remote_file"),
            persist_heartbeat=get("persist_heartbeat"),
            db_engine=get("DB_ENGINE"),
            sync_lab_to_basyx=get("aas_generator").sync_lab_to_basyx,
            logger=get("logging"),
            default_heartbeat_path=r"C:\LabStation\labstation\data\telemetry\heartbeat.json",
            default_events_path=r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl",
        )

    def format_sse_event(self, event: str, data: str) -> str:
        return self._get("_format_sse_event_impl")(event, data)

    def generate_heartbeat_stream(self, host: Dict[str, Any], include_events: bool):
        get = self._get
        return get("_generate_heartbeat_stream_impl")(
            host,
            include_events,
            poll_heartbeat=get("poll_heartbeat"),
            format_sse_event=get("_format_sse_event"),
            trust_error_type=get("WinRMTrustError"),
            missing_credentials_predicate=get("is_missing_winrm_credentials_error"),
            trust_error_payload=get("_winrm_trust_error_payload"),
            request_id=get("_request_id"),
            logger=get("logging"),
            sanitize_log_value=get("_sanitize_log_value"),
            credentials_required_message=get("WINRM_CREDENTIALS_REQUIRED_MESSAGE"),
            heartbeat_interval_seconds=get("HEARTBEAT_SSE_INTERVAL_SECONDS"),
            sleep=get("time").sleep,
        )

    def poll_all_hosts(self) -> Any:
        get = self._get
        return get("_poll_all_hosts_impl")(
            get("HOSTS"),
            get("poll_heartbeat"),
            get("logging"),
        )

    def load_persisted_heartbeat(
        self,
        lab_id: str,
        host: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        get = self._get
        return get("_load_persisted_heartbeat_impl")(
            get("DB_ENGINE"),
            lab_id,
            host,
            fetch_latest_heartbeat=get("_fetch_latest_heartbeat"),
        )


def create_heartbeat_runtime(providers: Mapping[str, Any]) -> HeartbeatRuntime:
    """Create a heartbeat adapter bound to live providers."""
    return HeartbeatRuntime(providers)


__all__ = ["HeartbeatRuntime", "create_heartbeat_runtime"]
