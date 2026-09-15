"""Explicit dependencies for durable session observations."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionObservationContext:
    """Dependencies required to build and operate the observation service."""

    get_session_observations_factory: Callable[[], Callable[..., Any]]
    get_db_engine: Callable[[], Any]
    get_guacamole_db_engine: Callable[[], Any]
    get_encrypt_secret: Callable[[], Callable[[str], str]]
    get_decrypt_secret: Callable[[], Callable[[str], str]]
    get_http_get: Callable[[], Callable[..., Any]]
    get_http_post: Callable[[], Callable[..., Any]]
    get_http_delete: Callable[[], Callable[..., Any]]
    get_sql_text: Callable[[], Callable[[str], Any]]
    get_integrity_error_type: Callable[[], type[BaseException]]
    get_enqueue_session_observation: Callable[
        [], Callable[[Mapping[str, Any]], bool]
    ]
    get_retry_delay: Callable[[], Callable[[int], int]]
    get_to_utc: Callable[[], Callable[[Any], Any]]
    get_now: Callable[[], Callable[[], Any]]
    get_current_epoch: Callable[[], Callable[[], float]]
    get_config: Callable[[], Mapping[str, Any]]
    get_logger: Callable[[], Any]
    get_service: Callable[[], Any]


__all__ = ["SessionObservationContext"]
