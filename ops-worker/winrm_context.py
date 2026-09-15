"""Explicit dependencies for the Ops Worker WinRM boundary."""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type


@dataclass(frozen=True)
class WinRMContext:
    """Dependencies required for policy, sessions and remote file commands."""

    get_winrm_port: Callable[[], int]
    get_allowed_transports: Callable[[], Collection[str]]
    coerce_bool: Callable[[Any], Optional[bool]]
    get_credential_ref_for_host: Callable[[Dict[str, Any]], str]
    get_load_credentials: Callable[[str], Optional[Dict[str, str]]]
    get_credentials_required_message: Callable[[], str]
    get_load_trust: Callable[[Dict[str, Any]], Tuple[str, Dict[str, Any]]]
    get_session_factory: Callable[[], Callable[..., Any]]
    get_ssl_error_type: Callable[[], Type[BaseException]]
    get_trust_error_type: Callable[[], Type[BaseException]]
    tls_error_code: str
    tls_error_message: str
    get_default_executable: Callable[[], Any]
    get_read_timeout_sec: Callable[[], Optional[int]]
    get_operation_timeout_sec: Callable[[], Optional[int]]
    get_logger: Callable[[], Any]
    clock: Callable[[], float]
    get_resolve_credentials: Callable[[], Callable[..., Tuple[str, str]]]
    get_resolve_policy: Callable[
        [], Callable[..., Tuple[bool, int, str]]
    ]
    get_create_session: Callable[[], Callable[..., Any]]
    get_run_method: Callable[[], Callable[..., Any]]
    get_build_labstation_command: Callable[
        [], Callable[[Any, str, List[Any]], Tuple[Any, List[Any]]]
    ]
    get_build_read_remote_file_command: Callable[[], Callable[[Any], str]]
    get_build_write_remote_file_command: Callable[
        [], Callable[[str, str], str]
    ]
    get_build_remove_remote_file_command: Callable[[], Callable[[Any], str]]


__all__ = ["WinRMContext"]
