"""Composition adapter for WinRM sessions and remote commands."""

from typing import Any, Dict, Optional, Tuple

from winrm_command_execution import run_winrm_method
from winrm_command_service import (
    read_remote_file,
    remove_remote_file,
    run_labstation_command,
    run_remote_powershell,
    write_remote_file,
)
from winrm_context import WinRMContext
from winrm_session_factory import create_winrm_session
from winrm_session_policy import (
    build_winrm_endpoint,
    resolve_winrm_connection_policy,
)
from winrm_credentials_resolution import resolve_winrm_credentials


class WinRMRuntime:
    """Expose WinRM operations through explicit dependencies."""

    def __init__(self, context: WinRMContext):
        self._context = context

    def winrm_connection_policy(
        self,
        host: Dict[str, Any],
        use_ssl: Optional[bool],
        port: Optional[int],
        transport: Optional[str],
    ) -> Tuple[bool, int, str]:
        context = self._context
        return resolve_winrm_connection_policy(
            host,
            use_ssl,
            port,
            transport,
            winrm_port=context.get_winrm_port(),
            allowed_transports=context.get_allowed_transports(),
            coerce_bool=context.coerce_bool,
        )

    def winrm_credentials(
        self,
        host: Dict[str, Any],
        user: Optional[str],
        password: Optional[str],
    ) -> Tuple[str, str]:
        context = self._context
        return resolve_winrm_credentials(
            host,
            user,
            password,
            credential_ref_for_host=context.get_credential_ref_for_host,
            load_credentials=context.get_load_credentials,
            required_message=context.get_credentials_required_message(),
        )

    def create_winrm_session(
        self,
        host: Dict[str, Any],
        user: str,
        password: str,
        transport: str,
        effective_port: int,
        *,
        read_timeout_sec: Optional[int] = None,
        operation_timeout_sec: Optional[int] = None,
    ) -> Any:
        context = self._context
        return create_winrm_session(
            host,
            user,
            password,
            transport,
            effective_port,
            read_timeout_sec=read_timeout_sec,
            operation_timeout_sec=operation_timeout_sec,
            load_trust=context.get_load_trust,
            session_factory=context.get_session_factory(),
        )

    def run_winrm_method(self, session: Any, method_name: str, *args: Any) -> Any:
        context = self._context
        return run_winrm_method(
            session,
            method_name,
            *args,
            ssl_error_type=context.get_ssl_error_type(),
            trust_error_factory=context.get_trust_error_type(),
            tls_error_code=context.tls_error_code,
            tls_error_message=context.tls_error_message,
        )

    def winrm_endpoint(
        self,
        host: Dict[str, Any],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> str:
        return build_winrm_endpoint(
            host,
            use_ssl,
            port,
            resolve_policy=self._context.get_resolve_policy(),
        )

    def run_labstation_command(
        self,
        host: Dict[str, Any],
        command: str,
        args: Optional[list],
        user: Optional[str],
        password: Optional[str],
        transport: Optional[str],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> Dict[str, Any]:
        context = self._context
        return run_labstation_command(
            host,
            command,
            args,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=context.get_resolve_credentials(),
            resolve_policy=context.get_resolve_policy(),
            create_session=context.get_create_session(),
            run_method=context.get_run_method(),
            build_command=context.get_build_labstation_command(),
            default_executable=context.get_default_executable(),
            read_timeout_sec=context.get_read_timeout_sec(),
            operation_timeout_sec=context.get_operation_timeout_sec(),
            logger=context.get_logger(),
            clock=context.clock,
        )

    def run_remote_powershell(
        self,
        host: Dict[str, Any],
        script: str,
        user: Optional[str],
        password: Optional[str],
        transport: Optional[str],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> str:
        context = self._context
        return run_remote_powershell(
            host,
            script,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=context.get_resolve_credentials(),
            resolve_policy=context.get_resolve_policy(),
            create_session=context.get_create_session(),
            run_method=context.get_run_method(),
            read_timeout_sec=context.get_read_timeout_sec(),
            operation_timeout_sec=context.get_operation_timeout_sec(),
        )

    def read_remote_file(
        self,
        host: Dict[str, Any],
        path: str,
        user: Optional[str],
        password: Optional[str],
        transport: Optional[str],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> str:
        context = self._context
        return read_remote_file(
            host,
            path,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=context.get_resolve_credentials(),
            resolve_policy=context.get_resolve_policy(),
            create_session=context.get_create_session(),
            run_method=context.get_run_method(),
            build_command=context.get_build_read_remote_file_command(),
            read_timeout_sec=context.get_read_timeout_sec(),
            operation_timeout_sec=context.get_operation_timeout_sec(),
        )

    def write_remote_file(
        self,
        host: Dict[str, Any],
        path: str,
        contents: str,
        user: Optional[str],
        password: Optional[str],
        transport: Optional[str],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> None:
        context = self._context
        return write_remote_file(
            host,
            path,
            contents,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=context.get_resolve_credentials(),
            resolve_policy=context.get_resolve_policy(),
            create_session=context.get_create_session(),
            run_method=context.get_run_method(),
            build_command=context.get_build_write_remote_file_command(),
            read_timeout_sec=context.get_read_timeout_sec(),
            operation_timeout_sec=context.get_operation_timeout_sec(),
        )

    def remove_remote_file(
        self,
        host: Dict[str, Any],
        path: str,
        user: Optional[str],
        password: Optional[str],
        transport: Optional[str],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> None:
        context = self._context
        return remove_remote_file(
            host,
            path,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=context.get_resolve_credentials(),
            resolve_policy=context.get_resolve_policy(),
            create_session=context.get_create_session(),
            run_method=context.get_run_method(),
            build_command=context.get_build_remove_remote_file_command(),
            read_timeout_sec=context.get_read_timeout_sec(),
            operation_timeout_sec=context.get_operation_timeout_sec(),
        )


def create_winrm_runtime(context: WinRMContext) -> WinRMRuntime:
    """Create a WinRM adapter bound to explicit dependencies."""
    return WinRMRuntime(context)


__all__ = ["WinRMRuntime", "create_winrm_runtime"]
