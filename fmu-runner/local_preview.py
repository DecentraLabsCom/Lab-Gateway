"""Isolated, opt-in local Executor previews; never registered outside local-dev.

Only the private loopback Gateway bridge holds the internal preview credential.
Browser clients still use one-use tickets and the normal WS session manager.
No preview JWT issuer or alternate Station execution protocol is introduced.
"""
import hashlib
import secrets
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from fmu_backend import BaseFmuBackend


class PreviewTickets:
    def __init__(self):
        self.tickets = {}

    def issue(self, access_key):
        access_key = BaseFmuBackend.validate_access_key(access_key)
        now = int(time.time())
        self.tickets = {key: value for key, value in self.tickets.items() if value[0] > now}
        if len(self.tickets) >= 128:
            raise HTTPException(429, "Too many outstanding local preview tickets")
        identifier = hashlib.sha256(access_key.encode()).hexdigest()[:24]
        claims = {"sub": "local-preview", "pucHash": "local-preview", "resourceType": "fmu", "labId": f"preview:{identifier}",
                  "reservationKey": f"preview:{identifier}", "accessKey": access_key,
                  "exp": now + 3600, "reservationEndsAt": now + 3600}
        ticket = "preview_" + secrets.token_urlsafe(32)
        self.tickets[ticket] = (now + 60, claims)
        return {"protocolVersion": "1.0", "gatewayWsUrl": "ws://127.0.0.1:8081/dev-fmu/sessions",
                "labId": claims["labId"], "reservationKey": claims["reservationKey"],
                "sessionTicket": ticket, "ticketExpiresAt": now + 60}

    def redeem(self, ticket, lab_id, reservation_key):
        entry = self.tickets.get(ticket)
        if not entry or entry[0] <= time.time():
            raise HTTPException(401, "Preview ticket is invalid or expired")
        claims = entry[1]
        if claims["labId"] != lab_id or claims["reservationKey"] != reservation_key:
            raise HTTPException(403, "Preview reservation mismatch")
        self.tickets.pop(ticket)
        return dict(claims)


class PreviewRequest(BaseModel):
    accessKey: str = Field(min_length=1, max_length=255)


def create_preview_router(tickets, internal_token):
    router = APIRouter()

    @router.post("/internal/dev/fmu/connection")
    async def connection(body: PreviewRequest, x_local_preview_token: str = Header(default="")):
        if not internal_token or not secrets.compare_digest(x_local_preview_token, internal_token):
            raise HTTPException(403, "Forbidden")
        from fastapi.responses import JSONResponse
        return JSONResponse(tickets.issue(body.accessKey), headers={"Cache-Control": "no-store"})

    return router
