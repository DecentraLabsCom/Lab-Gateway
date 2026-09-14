"""Live adapter composition for WinRM sessions and remote commands."""

from collections.abc import Mapping
from typing import Any, Dict, Optional, Tuple


class WinRMRuntime:
    """Resolve WinRM dependencies from a live provider namespace."""

    def __init__(self, providers: Mapping[str, Any]):
        self._providers = providers

    def _get(self, name: str) -> Any:
        return self._providers[name]

    def winrm_connection_policy(
        self,
        host: Dict[str, Any],
        use_ssl: Optional[bool],
        port: Optional[int],
        transport: Optional[str],
    ) -> Tuple[bool, int, str]:
        return self._get("_resolve_winrm_connection_policy_impl")(
            host,
            use_ssl,
            port,
            transport,
            winrm_port=self._get("WINRM_PORT"),
            allowed_transports=self._get("WINRM_ALLOWED_TRANSPORTS"),
            coerce_bool=self._get("_coerce_bool"),
        )

    def winrm_credentials(
        self,
        host: Dict[str, Any],
        user: Optional[str],
        password: Optional[str],
    ) -> Tuple[str, str]:
        return self._get("_resolve_winrm_credentials_impl")(
            host,
            user,
            password,
            credential_ref_for_host=self._get("credential_ref_for_host"),
            load_credentials=self._get("load_winrm_credentials"),
            required_message=self._get("WINRM_CREDENTIALS_REQUIRED_MESSAGE"),
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
        return self._get("_create_winrm_session_impl")(
            host,
            user,
            password,
            transport,
            effective_port,
            read_timeout_sec=read_timeout_sec,
            operation_timeout_sec=operation_timeout_sec,
            load_trust=self._get("load_winrm_trust"),
            session_factory=self._get("winrm").Session,
        )

    def run_winrm_method(self, session: Any, method_name: str, *args: Any) -> Any:
        return self._get("_run_winrm_method_impl")(
            session,
            method_name,
            *args,
            ssl_error_type=self._get("requests").exceptions.SSLError,
            trust_error_factory=self._get("WinRMTrustError"),
            tls_error_code="WINRM_TLS_FAILED",
            tls_error_message=self._get("WINRM_TLS_FAILED_MESSAGE"),
        )

    def winrm_endpoint(
        self,
        host: Dict[str, Any],
        use_ssl: Optional[bool],
        port: Optional[int],
    ) -> str:
        return self._get("_build_winrm_endpoint_impl")(
            host,
            use_ssl,
            port,
            resolve_policy=self._get("_winrm_connection_policy"),
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
        return self._get("_run_labstation_command_impl")(
            host,
            command,
            args,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=self._get("_winrm_credentials"),
            resolve_policy=self._get("_winrm_connection_policy"),
            create_session=self._get("create_winrm_session"),
            run_method=self._get("run_winrm_method"),
            build_command=self._get("_build_labstation_command_impl"),
            default_executable=self._get("DEFAULT_LABSTATION_EXE"),
            read_timeout_sec=self._get("WINRM_READ_TIMEOUT"),
            operation_timeout_sec=self._get("WINRM_OPERATION_TIMEOUT"),
            logger=self._get("logging"),
            clock=self._get("time").time,
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
        return self._get("_run_remote_powershell_impl")(
            host,
            script,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=self._get("_winrm_credentials"),
            resolve_policy=self._get("_winrm_connection_policy"),
            create_session=self._get("create_winrm_session"),
            run_method=self._get("run_winrm_method"),
            read_timeout_sec=self._get("WINRM_READ_TIMEOUT"),
            operation_timeout_sec=self._get("WINRM_OPERATION_TIMEOUT"),
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
        return self._get("_read_remote_file_impl")(
            host,
            path,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=self._get("_winrm_credentials"),
            resolve_policy=self._get("_winrm_connection_policy"),
            create_session=self._get("create_winrm_session"),
            run_method=self._get("run_winrm_method"),
            build_command=self._get("_build_read_remote_file_command_impl"),
            read_timeout_sec=self._get("WINRM_READ_TIMEOUT"),
            operation_timeout_sec=self._get("WINRM_OPERATION_TIMEOUT"),
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
        return self._get("_write_remote_file_impl")(
            host,
            path,
            contents,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=self._get("_winrm_credentials"),
            resolve_policy=self._get("_winrm_connection_policy"),
            create_session=self._get("create_winrm_session"),
            run_method=self._get("run_winrm_method"),
            build_command=self._get("_build_write_remote_file_command_impl"),
            read_timeout_sec=self._get("WINRM_READ_TIMEOUT"),
            operation_timeout_sec=self._get("WINRM_OPERATION_TIMEOUT"),
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
        return self._get("_remove_remote_file_impl")(
            host,
            path,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=self._get("_winrm_credentials"),
            resolve_policy=self._get("_winrm_connection_policy"),
            create_session=self._get("create_winrm_session"),
            run_method=self._get("run_winrm_method"),
            build_command=self._get("_build_remove_remote_file_command_impl"),
            read_timeout_sec=self._get("WINRM_READ_TIMEOUT"),
            operation_timeout_sec=self._get("WINRM_OPERATION_TIMEOUT"),
        )


def create_winrm_runtime(providers: Mapping[str, Any]) -> WinRMRuntime:
    """Create a WinRM adapter bound to a live provider namespace."""
    return WinRMRuntime(providers)


__all__ = ["WinRMRuntime", "create_winrm_runtime"]
