from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


def create_health_router(*, backend_health: Any, refresh_jwks: Any, auth_health: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        payload = await backend_health()
        try:
            await refresh_jwks()
        except HTTPException:
            pass
        auth_status = auth_health()
        checks = dict(payload.get("checks") or {})
        checks["jwks"] = auth_status["status"] == "UP"
        payload["checks"] = checks
        payload["auth"] = auth_status
        if auth_status["status"] == "DOWN":
            payload["status"] = "DOWN"
        elif auth_status["status"] != "UP":
            payload["status"] = "DEGRADED"
        return JSONResponse(
            content=payload,
            status_code=503 if payload.get("status") == "DOWN" else 200,
        )

    return router