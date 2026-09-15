"""Explicit dependencies for Ops Worker application hooks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppHooksContext:
    """Security, request and error-handling ports for the Flask application."""

    get_env_or_secret_file_impl: Callable[[], Callable[..., str]]
    get_logger: Callable[[], Any]
    get_sanitize_log_value_impl: Callable[[], Callable[[Any], str]]
    get_as_utc_datetime_impl: Callable[[], Callable[..., Any]]
    get_datetime: Callable[[], Any]
    get_timezone: Callable[[], Any]
    get_request_headers: Callable[[], Any]
    get_request_path: Callable[[], str]
    get_request_id_from_headers_impl: Callable[[], Callable[..., str]]
    get_internal_error_response_impl: Callable[[], Callable[..., Any]]
    get_request_id: Callable[[], Callable[[], str]]
    get_sanitize_log_value: Callable[[], Callable[[Any], str]]
    get_handle_unexpected_exception_impl: Callable[[], Callable[..., Any]]
    get_internal_error_response: Callable[[], Callable[..., Any]]
    get_requires_ops_internal_auth_impl: Callable[[], Callable[[str], bool]]
    get_check_ops_internal_auth_impl: Callable[[], Callable[..., Any]]
    get_ops_internal_auth_header: Callable[[], str]
    get_ops_internal_auth_token: Callable[[], str]
    get_requires_ops_internal_auth: Callable[[], Callable[[str], bool]]
    get_jsonify: Callable[[], Callable[..., Any]]


__all__ = ["AppHooksContext"]
