"""Pure builders for the PowerShell and LabStation WinRM commands."""

from typing import Any, List, Tuple


def build_labstation_command(
    executable: Any,
    command: str,
    args: List[Any],
) -> Tuple[Any, List[Any]]:
    """Return the executable and ordered arguments used by ``run_cmd``."""
    return executable, [command] + args


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
