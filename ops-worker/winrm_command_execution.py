"""WinRM method invocation and stable TLS error translation."""

from collections.abc import Callable
from typing import Any, Type

from winrm import Response


def _run_direct_command(session: Any, executable: str, arguments: Any) -> Response:
    """Run an executable through WinRS without the remote cmd.exe wrapper."""
    protocol = session.protocol
    shell_id = protocol.open_shell()
    command_id = None
    try:
        command_id = protocol.run_command(
            shell_id,
            executable,
            arguments,
            skip_cmd_shell=True,
        )
        return Response(protocol.get_command_output(shell_id, command_id))
    finally:
        if command_id is not None:
            protocol.cleanup_command(shell_id, command_id)
        protocol.close_shell(shell_id)


def run_winrm_method(
    session: Any,
    method_name: str,
    *args: Any,
    ssl_error_type: Type[BaseException],
    trust_error_factory: Callable[[str, str], BaseException],
    tls_error_code: str,
    tls_error_message: str,
) -> Any:
    """Run a WinRM operation while keeping TLS failures actionable and stable."""
    try:
        if method_name == "run_cmd_direct":
            return _run_direct_command(session, *args)
        return getattr(session, method_name)(*args)
    except ssl_error_type as exc:
        raise trust_error_factory(tls_error_code, tls_error_message) from exc
