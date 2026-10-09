import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_health_router(*, backend_health: Any, refresh_jwks: Any, auth_health: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health(lab_id: Optional[str] = Query(default=None, alias="labId")):
        payload = (
            await backend_health()
            if lab_id is None
            else await backend_health(lab_id=lab_id)
        )
        try:
            await refresh_jwks()
        except HTTPException as exc:
            logger.warning(
                "Unable to refresh JWKS while building health response (status %s)",
                exc.status_code,
            )
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
