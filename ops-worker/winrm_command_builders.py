"""Pure builders for PowerShell and LabStation WinRM commands."""

from typing import Any, List


def build_labstation_command(
    executable: Any,
    command: str,
    args: List[Any],
) -> str:
    """Build a PowerShell wrapper that preserves the executable and arguments.

    WinRS command-line argument handling is not reliable for Lab Station paths
    containing spaces. PowerShell's call operator and argument splatting keep
    the executable path and every argument as separate values, including
    values such as ``--reason=Remote order``.
    """
    executable_text = str(executable).strip()
    if len(executable_text) >= 2 and executable_text[0] == executable_text[-1] == '"':
        executable_text = executable_text[1:-1]

    values = [command, *args]
    powershell_args = ", ".join(_powershell_literal(value) for value in values)
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$labStationExe = {_powershell_literal(executable_text)}",
            f"$labStationArgs = @({powershell_args})",
            "& $labStationExe @labStationArgs",
            "$exitCode = $LASTEXITCODE",
            "if ($null -eq $exitCode) { $exitCode = 0 }",
            "exit $exitCode",
        ]
    )


def _powershell_literal(value: Any) -> str:
    """Return a single-quoted PowerShell literal safe for command arguments."""
    return "'" + str(value).replace("'", "''") + "'"


def build_read_remote_file_command(path: Any) -> str:
    escaped_path = str(path or "").replace("'", "''")
    return f"Get-Content -LiteralPath '{escaped_path}' -Raw -Encoding UTF8"


def build_write_remote_file_command(path: str, contents: str) -> str:
    escaped_path = path.replace("'", "''")
    escaped_contents = contents.replace("'", "''")
    return f"Set-Content -LiteralPath '{escaped_path}' -Value '{escaped_contents}' -Encoding UTF8"


def build_remove_remote_file_command(path: str) -> str:
    escaped_path = path.replace("'", "''")
    return f"if (Test-Path -LiteralPath '{escaped_path}') {{ Remove-Item -LiteralPath '{escaped_path}' -Force }}"
