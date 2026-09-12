"""Pure helpers for building the FMU proxy session configuration.

The proxy runtime consumes a small JSON document embedded in the generated
FMU.  Keeping URL derivation and payload construction here lets the HTTP
route retain ownership of authentication, reservation, ticket, and backend
orchestration while preserving the existing runtime contract.
"""

from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse


def derive_gateway_ws_url(
    claims: Mapping[str, Any],
    *,
    configured_url: str,
) -> str:
    """Resolve the gateway WebSocket endpoint from configuration or claims."""

    if configured_url:
        return configured_url

    aud = str(claims.get("aud") or "").strip()
    if not aud:
        raise ValueError("Missing aud claim required to derive gateway WS URL")

    parsed = urlparse(aud)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid aud claim required to derive gateway WS URL")

    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((ws_scheme, parsed.netloc, "/fmu/api/v1/fmu/sessions", "", "", ""))


def build_proxy_session_config(
    *,
    fmi_version: str,
    gateway_ws_url: str,
    lab_id: str,
    reservation_key: str,
    session_ticket: str,
    ticket_expires_at: int,
    time_mode: str = "simtime",
) -> dict[str, Any]:
    """Build the config payload consumed by the proxy runtime."""

    return {
        "protocolVersion": "1.0",
        "fmiVersion": fmi_version,
        "gatewayWsUrl": gateway_ws_url,
        "labId": lab_id,
        "reservationKey": reservation_key,
        "sessionTicket": session_ticket,
        "ticketExpiresAt": ticket_expires_at,
        "timeMode": time_mode,
    }
