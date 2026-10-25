"""Isolated, opt-in local Executor previews; never registered outside local-dev.

Only the private loopback Gateway bridge holds the internal preview credential.
Browser clients still use one-use tickets and the normal WS session manager.
No preview JWT issuer or alternate Station execution protocol is introduced.
"""
import hashlib
import secrets
import time
from typing import Any, NotRequired, TypedDict, cast

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from fmu_backend import BaseFmuBackend


class PreviewClaims(TypedDict):
    sub: str
    pucHash: str
    resourceType: str
    labId: str
    reservationKey: str
    accessKey: str
    exp: NotRequired[int]
    reservationEndsAt: NotRequired[int]


class PreviewGrant(TypedDict):
    protocolVersion: str
    gatewayWsUrl: str
    labId: str
    reservationKey: str
    sessionTicket: str
    ticketExpiresAt: int


class PreviewTickets:
    def __init__(self):
        self.tickets: dict[str, tuple[int, PreviewClaims]] = {}

    @staticmethod
    def claims_for_access_key(access_key: str) -> PreviewClaims:
        access_key = BaseFmuBackend.validate_access_key(access_key)
        identifier = hashlib.sha256(access_key.encode()).hexdigest()[:24]
        return {
            "sub": "local-preview",
            "pucHash": f"local-preview-{identifier}",
            "resourceType": "fmu",
            "labId": f"local_demo_{identifier}",
            "reservationKey": f"local-preview-{identifier}",
            "accessKey": access_key,
        }

    def issue(self, access_key: str) -> PreviewGrant:
        now = int(time.time())
        self.tickets = {key: value for key, value in self.tickets.items() if value[0] > now}
        if len(self.tickets) >= 128:
            raise HTTPException(429, "Too many outstanding local preview tickets")
        claims = self.claims_for_access_key(access_key)
        expires_at = now + 3600
        claims["exp"] = expires_at
        claims["reservationEndsAt"] = expires_at
        ticket = "preview_" + secrets.token_urlsafe(32)
        self.tickets[ticket] = (now + 60, claims)
        return {"protocolVersion": "1.0", "gatewayWsUrl": "ws://127.0.0.1:8081/dev-fmu/sessions",
                "labId": claims["labId"], "reservationKey": claims["reservationKey"],
                "sessionTicket": ticket, "ticketExpiresAt": now + 60}

    def redeem(self, ticket: str, lab_id: str, reservation_key: str) -> PreviewClaims:
        entry = self.tickets.get(ticket)
        if not entry or entry[0] <= time.time():
            raise HTTPException(401, "Preview ticket is invalid or expired")
        claims = entry[1]
        if claims["labId"] != lab_id or claims["reservationKey"] != reservation_key:
            raise HTTPException(403, "Preview reservation mismatch")
        self.tickets.pop(ticket)
        return cast(PreviewClaims, dict(claims))


class PreviewRequest(BaseModel):
    accessKey: str = Field(min_length=1, max_length=255)


def create_preview_router(
    tickets: PreviewTickets,
    internal_token: str,
    *,
    ensure_aas_policy: Any = None,
    get_access_policy: Any = None,
    stream_simulation: Any = None,
):
    router = APIRouter()

    def require_internal_token(token: str) -> None:
        if not internal_token or not secrets.compare_digest(token, internal_token):
            raise HTTPException(403, "Forbidden")

    async def prepare_preview(access_key: str) -> tuple[PreviewClaims, dict[str, Any]]:
        claims = tickets.claims_for_access_key(access_key)
        expires_at = int(time.time()) + 3600
        claims["exp"] = expires_at
        claims["reservationEndsAt"] = expires_at
        if ensure_aas_policy is None:
            raise HTTPException(503, "Local AAS access policy provisioning is unavailable")
        policy = await ensure_aas_policy(claims)
        if not isinstance(policy, dict) or not str(policy.get("policySource") or "").startswith("aas-"):
            raise HTTPException(503, "Local AAS access policy is unavailable")
        return claims, policy

    @router.post("/internal/dev/fmu/connection")
    async def connection(body: PreviewRequest, x_local_preview_token: str = Header(default="")):
        require_internal_token(x_local_preview_token)
        await prepare_preview(body.accessKey)
        from fastapi.responses import JSONResponse
        return JSONResponse(tickets.issue(body.accessKey), headers={"Cache-Control": "no-store"})

    @router.post("/internal/dev/fmu/access")
    async def access(body: PreviewRequest, x_local_preview_token: str = Header(default="")):
        require_internal_token(x_local_preview_token)
        claims, policy = await prepare_preview(body.accessKey)
        if get_access_policy is None:
            raise HTTPException(503, "Local FMU access metadata is unavailable")
        result = await get_access_policy(claims, policy)
        if not isinstance(result, dict):
            raise HTTPException(503, "Local FMU access metadata is unavailable")
        return result

    @router.get("/internal/dev/fmu/access")
    async def access_from_gateway_headers(
        x_local_preview_token: str = Header(default=""),
        x_fmu_access_key: str = Header(default=""),
    ):
        require_internal_token(x_local_preview_token)
        claims, policy = await prepare_preview(x_fmu_access_key)
        if get_access_policy is None:
            raise HTTPException(503, "Local FMU access metadata is unavailable")
        result = await get_access_policy(claims, policy)
        if not isinstance(result, dict):
            raise HTTPException(503, "Local FMU access metadata is unavailable")
        return result

    @router.post("/internal/dev/fmu/simulations/stream")
    async def stream(
        request: Request,
        x_local_preview_token: str = Header(default=""),
        x_fmu_access_key: str = Header(default=""),
    ):
        require_internal_token(x_local_preview_token)
        claims, policy = await prepare_preview(x_fmu_access_key)
        if stream_simulation is None:
            raise HTTPException(503, "Local FMU simulation is unavailable")
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(400, "Simulation request must be valid JSON") from exc
        return await stream_simulation(request, payload, claims, policy)

    return router
