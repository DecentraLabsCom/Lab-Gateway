"""Heartbeat path discovery and fallback composition."""

import json
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Optional


HEARTBEAT_TASK_SCRIPT = r"""
$task = Get-ScheduledTask -TaskPath '\LabStation\' -TaskName 'BackgroundService' -ErrorAction Stop
$action = @($task.Actions)[0]
$execute = [string]$action.Execute
$arguments = [string]$action.Arguments
$heartbeatPath = ''
if ($arguments -match '"([^"]*\\LabStation\.ahk)"') {
    $root = Split-Path -Parent $Matches[1]
    $heartbeatPath = Join-Path $root 'data\telemetry\heartbeat.json'
} elseif ($execute -match '(?i)LabStation\.exe$') {
    $root = Split-Path -Parent $execute.Trim('"')
    $heartbeatPath = Join-Path $root 'data\telemetry\heartbeat.json'
}
[pscustomobject]@{
    execute = $execute
    arguments = $arguments
    heartbeatPath = $heartbeatPath
} | ConvertTo-Json -Compress
"""


def query_labstation_task_heartbeat_path(
    host: Dict[str, Any],
    *,
    run_remote_powershell: Callable[..., str],
    parse_json: Callable[[str], Any],
    logger: Any,
) -> Optional[str]:
    """Derive a heartbeat path from the LabStation scheduled task."""
    try:
        raw = run_remote_powershell(
            host,
            HEARTBEAT_TASK_SCRIPT,
            None,
            None,
            None,
            None,
            None,
        )
        parsed = parse_json(raw)
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Unable to derive Lab Station heartbeat path from scheduled task: %s", exc)
        return None
    path = str(parsed.get("heartbeatPath") or "").strip() if isinstance(parsed, dict) else ""
    return path or None


def build_heartbeat_path_candidates(
    host: Dict[str, Any],
    *,
    query_task_path: Callable[[Dict[str, Any]], Optional[str]],
    configured_paths: Sequence[str],
) -> List[str]:
    """Put the installed task path first, followed by unique configured paths."""
    candidates: List[str] = []
    task_path = query_task_path(host)
    if task_path:
        candidates.append(task_path)
    for path in configured_paths:
        if path and path not in candidates:
            candidates.append(path)
    return candidates
