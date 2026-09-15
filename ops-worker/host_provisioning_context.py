"""Explicit dependencies for the Lab Station host provisioning boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, List, Optional, Pattern, Tuple


@dataclass(frozen=True)
class HostProvisioningContext:
    """Dependencies required to validate and build a provisioned host."""

    get_name_pattern: Callable[[], Pattern[str]]
    normalize_mac: Callable[[Any], str]
    normalize_trust_ref: Callable[[Any], str]
    get_sanitize_host_name: Callable[
        [Any, Optional[Any]], Tuple[Optional[str], Optional[str]]
    ]
    get_normalize_labs: Callable[[Any], List[str]]
    get_validate_labs_against_candidates: Callable[[List[str], Any], Optional[str]]
    default_heartbeat_path: str = r"C:\LabStation\labstation\data\telemetry\heartbeat.json"
    default_events_path: str = (
        r"C:\LabStation\labstation\data\telemetry\session-guard-events.jsonl"
    )


__all__ = ["HostProvisioningContext"]
