"""FMU Station enrollment policy and remote provisioning helpers.

The Gateway owns one FMU Station endpoint and one internal token.  This module
keeps the policy independent from Flask so the single-station invariant and
the PowerShell contract can be tested without a live WinRM server.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse


_TOKEN_MIN_LENGTH = 32
_TOKEN_MAX_LENGTH = 512
_TOKEN_RE = re.compile(r"^[^\r\n]{32,512}$")


class FmuStationEnrollmentError(ValueError):
    """A safe, public enrollment error with a stable API code."""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class FmuStationConfig:
    backend_mode: str
    base_url: str
    configured_host: str
    internal_token: str


def _normalized(value: Any) -> str:
    return str(value or "").strip().rstrip(".").casefold()


def _valid_base_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _valid_token(value: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(value)) and len(value) >= _TOKEN_MIN_LENGTH


def _station_url_hostname(base_url: str) -> str:
    try:
        return _normalized(urlparse(base_url).hostname)
    except ValueError:
        return ""


def _host_matches_target(host: Mapping[str, Any], target: str) -> bool:
    normalized_target = _normalized(target)
    return bool(normalized_target) and normalized_target in {
        _normalized(host.get("name")),
        _normalized(host.get("address")),
    }


def resolve_station_host(
    hosts: Iterable[Mapping[str, Any]],
    *,
    configured_host: str,
    base_url: str,
) -> Optional[Mapping[str, Any]]:
    """Resolve the one configured Station to exactly one registered host."""
    target = _normalized(configured_host) or _station_url_hostname(base_url)
    if not target:
        return None
    matches = [host for host in hosts if _host_matches_target(host, target)]
    return matches[0] if len(matches) == 1 else None


def public_station_status(
    config: FmuStationConfig,
    hosts: Iterable[Mapping[str, Any]],
    *,
    runner_health: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return status suitable for Lab Manager; never return the token."""
    station_host = resolve_station_host(
        hosts,
        configured_host=config.configured_host,
        base_url=config.base_url,
    )
    health = runner_health if isinstance(runner_health, Mapping) else {}
    checks = health.get("checks") if isinstance(health.get("checks"), Mapping) else {}
    station_authenticated = checks.get("stationAuthentication") is True
    link_status = (
        "linked"
        if station_authenticated
        else "unlinked"
        if "stationAuthentication" in checks
        else "unknown"
    )
    backend_mode = config.backend_mode or "station"
    endpoint_valid = _valid_base_url(config.base_url)
    token_configured = bool(config.internal_token)
    configured = (
        backend_mode == "station"
        and endpoint_valid
        and _valid_token(config.internal_token)
        and station_host is not None
    )
    return {
        "backendMode": backend_mode,
        "configured": configured,
        "singleStationPerGateway": True,
        "endpoint": config.base_url if endpoint_valid else "",
        "stationHost": str((station_host or {}).get("name") or ""),
        "stationAddress": str((station_host or {}).get("address") or ""),
        "linked": station_authenticated,
        "linkedHost": str((station_host or {}).get("name") or "") if station_authenticated else "",
        "linkStatus": link_status,
        "tokenConfigured": token_configured,
        "runner": {
            "status": str(health.get("status") or "UNKNOWN").upper(),
            "stationHealth": checks.get("stationHealth") is True,
            "stationAuthenticated": station_authenticated,
        },
    }


def build_fmu_station_provision_script(token: str) -> str:
    """Build a token-safe script that updates machine env and restarts Station."""
    if not _valid_token(token):
        raise FmuStationEnrollmentError(
            "FMU_STATION_TOKEN_INVALID",
            "FMU Station internal token is missing or invalid",
            503,
        )

    encoded_token = base64.b64encode(token.encode("utf-8")).decode("ascii")
    return fr"""
$ErrorActionPreference = 'Stop'
$encodedToken = '{encoded_token}'
$token = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedToken))
[Environment]::SetEnvironmentVariable('FMU_INTERNAL_TOKEN', $token, 'Machine')
if ([Environment]::GetEnvironmentVariable('FMU_INTERNAL_TOKEN', 'Machine') -ne $token) {{
    throw 'FMU Station machine token could not be persisted'
}}
$taskPath = '\\LabStation\\'
$taskName = 'BackgroundService'
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State -eq 'Running') {{
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(30)
    do {{
        Start-Sleep -Milliseconds 250
        $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    }} while ($task.State -eq 'Running' -and (Get-Date) -lt $deadline)
    if ($task.State -eq 'Running') {{
        throw 'Lab Station background service did not stop in time'
    }}
}}
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
Write-Output 'fmu-station-provisioned'
""".strip()


def build_fmu_station_release_script() -> str:
    """Build a script that removes the machine token and restarts Station."""
    return r"""
$ErrorActionPreference = 'Stop'
[Environment]::SetEnvironmentVariable('FMU_INTERNAL_TOKEN', $null, 'Machine')
if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable('FMU_INTERNAL_TOKEN', 'Machine'))) {
    throw 'FMU Station machine token could not be removed'
}
$taskPath = '\LabStation\'
$taskName = 'BackgroundService'
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State -eq 'Running') {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    } while ($task.State -eq 'Running' -and (Get-Date) -lt $deadline)
    if ($task.State -eq 'Running') {
        throw 'Lab Station background service did not stop in time'
    }
}
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
Write-Output 'fmu-station-released'
""".strip()


def _resolve_requested_station(
    payload: Mapping[str, Any],
    *,
    config: FmuStationConfig,
    hosts: Iterable[Mapping[str, Any]],
    require_token: bool,
) -> Mapping[str, Any]:
    if config.backend_mode != "station":
        raise FmuStationEnrollmentError(
            "FMU_STATION_BACKEND_INACTIVE",
            "FMU Station operation requires FMU_BACKEND_MODE=station",
            409,
        )
    if not _valid_base_url(config.base_url):
        raise FmuStationEnrollmentError(
            "FMU_STATION_NOT_CONFIGURED",
            "The Gateway FMU Station endpoint is not configured",
            503,
        )
    if require_token and not _valid_token(config.internal_token):
        raise FmuStationEnrollmentError(
            "FMU_STATION_TOKEN_INVALID",
            "FMU Station internal token is missing or invalid",
            503,
        )

    requested_host = str(payload.get("host") or payload.get("hostName") or "").strip()
    if not requested_host or len(requested_host) > 255:
        raise FmuStationEnrollmentError(
            "FMU_STATION_HOST_REQUIRED",
            "A registered Lab Station host is required",
            400,
        )

    host_list = list(hosts)
    selected = next(
        (
            host
            for host in host_list
            if _normalized(host.get("name")) == _normalized(requested_host)
        ),
        None,
    )
    configured_station = resolve_station_host(
        host_list,
        configured_host=config.configured_host,
        base_url=config.base_url,
    )
    if selected is None:
        raise FmuStationEnrollmentError(
            "FMU_STATION_HOST_NOT_FOUND",
            "The selected FMU Station host is not registered",
            404,
        )
    if configured_station is None or _normalized(selected.get("name")) != _normalized(
        configured_station.get("name")
    ):
        raise FmuStationEnrollmentError(
            "FMU_STATION_HOST_MISMATCH",
            "The selected host is not this Gateway's configured FMU Station",
            409,
        )
    return selected


def enroll_fmu_station(
    payload: Mapping[str, Any],
    *,
    config: FmuStationConfig,
    hosts: Iterable[Mapping[str, Any]],
    run_remote_powershell: Callable[..., Any],
) -> dict[str, Any]:
    """Provision the Gateway token on its one configured Station host."""
    selected = _resolve_requested_station(
        payload,
        config=config,
        hosts=hosts,
        require_token=True,
    )

    run_remote_powershell(
        host=selected,
        script=build_fmu_station_provision_script(config.internal_token),
        user=None,
        password=None,
        transport=None,
        use_ssl=None,
        port=None,
    )
    return {
        "enrolled": True,
        "host": str(selected.get("name") or ""),
        "address": str(selected.get("address") or ""),
        "restartRequested": True,
    }


def release_fmu_station(
    payload: Mapping[str, Any],
    *,
    config: FmuStationConfig,
    hosts: Iterable[Mapping[str, Any]],
    run_remote_powershell: Callable[..., Any],
) -> dict[str, Any]:
    """Remove the FMU token from the one configured Station host."""
    selected = _resolve_requested_station(
        payload,
        config=config,
        hosts=hosts,
        require_token=False,
    )
    run_remote_powershell(
        host=selected,
        script=build_fmu_station_release_script(),
        user=None,
        password=None,
        transport=None,
        use_ssl=None,
        port=None,
    )
    return {
        "released": True,
        "host": str(selected.get("name") or ""),
        "address": str(selected.get("address") or ""),
        "restartRequested": True,
    }


__all__ = [
    "FmuStationConfig",
    "FmuStationEnrollmentError",
    "build_fmu_station_provision_script",
    "build_fmu_station_release_script",
    "enroll_fmu_station",
    "public_station_status",
    "release_fmu_station",
    "resolve_station_host",
]
