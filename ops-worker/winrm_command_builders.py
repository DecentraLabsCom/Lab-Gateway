"""Pure builders for the PowerShell and LabStation WinRM commands."""

from typing import Any, List, Tuple


def _quote_winrm_token(value: Any) -> str:
    """Quote one token for pywinrm's cmd-backed argument string."""
    text = str(value)
    if text == "":
        return '""'
    if not any(char.isspace() or char in '"&|<>()^' for char in text):
        return text
    return '"' + text.replace('"', '\\"') + '"'


def build_labstation_command(
    executable: Any,
    command: str,
    args: List[Any],
) -> Tuple[Any, List[Any]]:
    """Return a cmd-safe executable and ordered arguments for ``run_cmd``.

    pywinrm sends the executable and arguments to the Windows command shell.
    Paths such as ``C:\\Lab Station\\LabStation.exe`` and arguments containing
    spaces must therefore remain single command-line tokens.
    """
    quoted_executable = _quote_winrm_token(executable)
    quoted_args = [_quote_winrm_token(arg) for arg in args]
    return quoted_executable, [command] + quoted_args


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
