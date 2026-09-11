import re
from typing import Any, Optional

from fastapi import HTTPException


def build_stream_error_payload(exc: Exception, *, sim_id: Optional[str] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "error"}
    if sim_id:
        payload["simId"] = sim_id

    detail = "Simulation failed"
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        message = exc.detail.get("error")
        if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", code):
            payload["code"] = code
        if isinstance(message, str) and 0 < len(message) <= 256:
            detail = message
    payload["detail"] = detail
    return payload