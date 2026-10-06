"""Stable, transport-neutral errors for station management operations."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StationError(Exception):
    code: str
    message: str
    transport: Optional[str] = None

    def __str__(self) -> str:
        return self.message


class StationTrustRequired(StationError):
    def __init__(self, message: str = "SSH host key confirmation is required"):
        super().__init__("STATION_TRUST_REQUIRED", message, "ssh")


class StationTrustMismatch(StationError):
    def __init__(self, message: str = "SSH host key does not match confirmed trust"):
        super().__init__("STATION_TRUST_MISMATCH", message, "ssh")


class StationAuthenticationFailed(StationError):
    def __init__(self, message: str = "Station authentication failed"):
        super().__init__("STATION_AUTH_FAILED", message, "ssh")


class StationUnreachable(StationError):
    def __init__(self, message: str = "Station management endpoint is unreachable"):
        super().__init__("STATION_UNREACHABLE", message, "ssh")


class StationCommandRejected(StationError):
    def __init__(self, message: str = "Station command is not allowlisted"):
        super().__init__("STATION_COMMAND_REJECTED", message, "ssh")
