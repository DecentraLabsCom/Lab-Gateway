"""Explicit dependencies for the Lab Station host provisioning boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, Pattern, Tuple

from runtime_values import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_HEARTBEAT_PATH,
    DEFAULT_LABSTATION_EXE,
    DEFAULT_LOCAL_MODE_FLAG_PATH,
)


@dataclass(frozen=True)
class HostProvisioningContext:
    """Dependencies required to validate and build a provisioned host."""

    get_name_pattern: Callable[[], Pattern[str]]
    normalize_mac: Callable[[Any], str]
    normalize_trust_ref: Callable[[Any], str]
    get_sanitize_host_name: Callable[
        [Any, Optional[Any]], Tuple[Optional[str], Optional[str]]
    ]
    default_heartbeat_path: str = DEFAULT_HEARTBEAT_PATH
    default_events_path: str = DEFAULT_EVENTS_PATH
    default_labstation_exe: str = DEFAULT_LABSTATION_EXE
    default_local_mode_flag_path: str = DEFAULT_LOCAL_MODE_FLAG_PATH


__all__ = ["HostProvisioningContext"]
