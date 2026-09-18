"""Explicit dependencies for the Lab Station heartbeat boundary."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Type

from runtime_values import DEFAULT_EVENTS_PATH, DEFAULT_HEARTBEAT_PATH


class HostRegistryProtocol(Protocol):
    """Minimal registry surface required by background heartbeat polling."""

    def all_hosts(self) -> Iterable[Dict[str, Any]]:
        ...


@dataclass(frozen=True)
class HeartbeatContext:
    """Dependencies required by polling, persistence, SSE and history lookup."""

    parse_datetime: Callable[[str], Any]
    utc_timezone: Any
    now: Callable[[], Any]
    sql_text: Callable[[str], Any]
    json_dumps: Callable[[Any], str]
    read_remote_file: Callable[..., str]
    get_db_engine: Callable[[], Any]
    sync_lab_to_basyx: Callable[..., Dict[str, Any]]
    resolve_lab_ids_for_host: Callable[[Mapping[str, Any]], Any]
    get_logger: Callable[[], Any]
    get_host_registry: Callable[[], HostRegistryProtocol]
    get_persist_heartbeat: Callable[..., Any]
    get_poll_heartbeat: Callable[..., Dict[str, Any]]
    fetch_latest_heartbeat: Callable[[Any, str], Optional[Dict[str, Any]]]
    trust_error_type: Type[BaseException]
    missing_credentials_predicate: Callable[[BaseException], bool]
    trust_error_payload: Callable[[Any, str], Dict[str, Any]]
    request_id: Callable[[], str]
    sanitize_log_value: Callable[[Any], str]
    credentials_required_message: str
    heartbeat_interval_seconds: float
    sleep: Callable[[float], None]
    default_heartbeat_path: str = DEFAULT_HEARTBEAT_PATH
    default_events_path: str = DEFAULT_EVENTS_PATH


__all__ = ["HeartbeatContext", "HostRegistryProtocol"]
