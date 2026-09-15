"""Explicit dependencies for Guacamole integration boundaries."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuacamoleContext:
    """Dependencies required by the Guacamole catalog and user operations."""

    get_load_connections_impl: Callable[[], Callable[..., Any]]
    get_db_engine: Callable[[], Any]
    get_sql_text: Callable[[], Callable[[str], Any]]
    get_logger: Callable[[], Any]
    get_request_headers: Callable[[], Any]
    get_check_auth_impl: Callable[[], Callable[..., Any]]
    get_expected_token: Callable[[], str]
    get_token_header: Callable[[], str]
    get_jsonify: Callable[[], Callable[..., Any]]
    get_parse_selector_impl: Callable[[], Callable[..., Any]]
    get_selector_pattern: Callable[[], Any]
    get_safe_connection_response_impl: Callable[[], Callable[..., Any]]
    get_provision_impl: Callable[[], Callable[..., Any]]
    get_parse_selector: Callable[[], Callable[..., Any]]
    get_resolve_connection: Callable[[], Callable[..., Any]]
    get_safe_connection_response: Callable[[], Callable[..., Any]]
    get_datetime: Callable[[], Any]
    get_timezone: Callable[[], Any]
    get_delete_impl: Callable[[], Callable[..., Any]]
    get_cleanup_impl: Callable[[], Callable[..., Any]]


__all__ = ["GuacamoleContext"]
