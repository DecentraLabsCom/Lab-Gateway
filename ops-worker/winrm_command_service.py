"""LabStation command execution with explicit WinRM dependencies."""

from collections.abc import Callable
from typing import Any, Dict, List, Optional, Tuple


def run_labstation_command(
    host: Dict[str, Any],
    command: str,
    args: Optional[List[Any]],
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
    create_session: Callable[..., Any],
    run_method: Callable[..., Any],
    build_command: Callable[[Any, str, List[Any]], Tuple[Any, List[Any]]],
    default_executable: Any,
    read_timeout_sec: Optional[int],
    operation_timeout_sec: Optional[int],
    logger: Any,
    clock: Callable[[], float],
) -> Dict[str, Any]:
    """Execute a LabStation command while preserving the worker response shape."""
    user, password = resolve_credentials(host, user, password)

    _, effective_port, effective_transport = resolve_policy(
        host, use_ssl, port, transport
    )
    endpoint = f"https://{host.get('address')}:{effective_port}/wsman"
    executable = host.get("labstation_exe", default_executable)
    command_args = args or []

    logger.info(
        "Executing %s %s on %s via %s",
        str(executable).replace("\r", "\\r").replace("\n", "\\n"),
        str(command).replace("\r", "\\r").replace("\n", "\\n"),
        str(host.get("name")).replace("\r", "\\r").replace("\n", "\\n"),
        str(endpoint).replace("\r", "\\r").replace("\n", "\\n"),
    )
    start = clock()
    session = create_session(
        host,
        user,
        password,
        effective_transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
    )
    executable, command_args = build_command(executable, command, command_args)
    result = run_method(session, "run_cmd", executable, command_args)
    duration_ms = int((clock() - start) * 1000)

    return {
        "exit_code": result.status_code,
        "stdout": (result.std_out or b"").decode("utf-8", errors="ignore"),
        "stderr": (result.std_err or b"").decode("utf-8", errors="ignore"),
        "duration_ms": duration_ms,
    }


def _resolve_connection(
    host: Dict[str, Any],
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
) -> Tuple[str, str, str, int]:
    resolved_user, resolved_password = resolve_credentials(host, user, password)
    _, effective_port, effective_transport = resolve_policy(
        host, use_ssl, port, transport
    )
    return resolved_user, resolved_password, effective_transport, effective_port


def _decode_output(value: Any) -> str:
    return (value or b"").decode("utf-8", errors="ignore")


def _run_powershell_result(result: Any, *, operation: str) -> str:
    if result.status_code != 0:
        raise RuntimeError(
            f"WinRM {operation} failed ({result.status_code}): "
            f"{_decode_output(result.std_err)}"
        )
    return _decode_output(result.std_out)


def run_remote_powershell(
    host: Dict[str, Any],
    script: str,
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
    create_session: Callable[..., Any],
    run_method: Callable[..., Any],
    read_timeout_sec: Optional[int],
    operation_timeout_sec: Optional[int],
) -> str:
    resolved_user, resolved_password, effective_transport, effective_port = (
        _resolve_connection(
            host,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=resolve_credentials,
            resolve_policy=resolve_policy,
        )
    )
    session = create_session(
        host,
        resolved_user,
        resolved_password,
        effective_transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
    )
    result = run_method(session, "run_ps", script)
    return _run_powershell_result(result, operation="PowerShell")


def read_remote_file(
    host: Dict[str, Any],
    path: str,
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
    create_session: Callable[..., Any],
    run_method: Callable[..., Any],
    build_command: Callable[[Any], str],
    read_timeout_sec: Optional[int],
    operation_timeout_sec: Optional[int],
) -> str:
    resolved_user, resolved_password, effective_transport, effective_port = (
        _resolve_connection(
            host,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=resolve_credentials,
            resolve_policy=resolve_policy,
        )
    )
    script = build_command(path)
    session = create_session(
        host,
        resolved_user,
        resolved_password,
        effective_transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
    )
    result = run_method(session, "run_ps", script)
    return _run_powershell_result(result, operation="read")


def write_remote_file(
    host: Dict[str, Any],
    path: str,
    contents: str,
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
    create_session: Callable[..., Any],
    run_method: Callable[..., Any],
    build_command: Callable[[str, str], str],
    read_timeout_sec: Optional[int],
    operation_timeout_sec: Optional[int],
) -> None:
    resolved_user, resolved_password, effective_transport, effective_port = (
        _resolve_connection(
            host,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=resolve_credentials,
            resolve_policy=resolve_policy,
        )
    )
    script = build_command(path, contents)
    session = create_session(
        host,
        resolved_user,
        resolved_password,
        effective_transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
    )
    result = run_method(session, "run_ps", script)
    _run_powershell_result(result, operation="write")


def remove_remote_file(
    host: Dict[str, Any],
    path: str,
    user: Optional[str],
    password: Optional[str],
    transport: Optional[str],
    use_ssl: Optional[bool],
    port: Optional[int],
    *,
    resolve_credentials: Callable[
        [Dict[str, Any], Optional[str], Optional[str]], Tuple[str, str]
    ],
    resolve_policy: Callable[
        [Dict[str, Any], Optional[bool], Optional[int], Optional[str]],
        Tuple[bool, int, str],
    ],
    create_session: Callable[..., Any],
    run_method: Callable[..., Any],
    build_command: Callable[[Any], str],
    read_timeout_sec: Optional[int],
    operation_timeout_sec: Optional[int],
) -> None:
    resolved_user, resolved_password, effective_transport, effective_port = (
        _resolve_connection(
            host,
            user,
            password,
            transport,
            use_ssl,
            port,
            resolve_credentials=resolve_credentials,
            resolve_policy=resolve_policy,
        )
    )
    script = build_command(path)
    session = create_session(
        host,
        resolved_user,
        resolved_password,
        effective_transport,
        effective_port,
        read_timeout_sec=read_timeout_sec,
        operation_timeout_sec=operation_timeout_sec,
    )
    result = run_method(session, "run_ps", script)
    _run_powershell_result(result, operation="remove")
