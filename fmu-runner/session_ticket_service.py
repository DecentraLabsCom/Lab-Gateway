from typing import Any, Optional

from fastapi import HTTPException


async def issue_session_ticket(
    authorization: str,
    *,
    lab_id: str,
    reservation_key: Optional[str],
    request_id: Optional[str] = None,
    issue_url: str,
    build_payload: Any,
    post_request: Any,
    extract_error_text: Any,
    coerce_epoch_seconds: Any,
    normalize_ticket_id: Any,
    logger: Any,
) -> tuple[str, int]:
    payload = build_payload(
        lab_id=lab_id,
        reservation_key=reservation_key,
    )

    response = await post_request(
        issue_url,
        payload=payload,
        authorization=authorization,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Unable to issue session ticket: {extract_error_text(response)}",
        )

    data = response.json()
    session_ticket = str(data.get("sessionTicket") or "").strip()
    expires_at = coerce_epoch_seconds(data.get("expiresAt"))
    if not session_ticket or expires_at is None:
        raise HTTPException(status_code=500, detail="Invalid session ticket response from auth service")
    logger.info(
        "Issued FMU session ticket request_id=%s lab_id=%s reservation_key=%s ticket_id=%s expires_at=%s",
        str(request_id or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
        str(reservation_key or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(normalize_ticket_id(session_ticket) or "-").replace("\r", "\\r").replace("\n", "\\n"),
        expires_at,
    )
    return session_ticket, expires_at


async def redeem_session_ticket(
    *,
    session_ticket: str,
    lab_id: Optional[str],
    reservation_key: Optional[str],
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    redeem_url: str,
    build_payload: Any,
    post_request: Any,
    observer_authorization: Any,
    extract_error_payload: Any,
    normalize_ticket_id: Any,
    logger: Any,
) -> dict:
    payload = build_payload(
        session_ticket=session_ticket,
        lab_id=lab_id,
        reservation_key=reservation_key,
    )

    response = await post_request(
        redeem_url,
        payload=payload,
        authorization=observer_authorization(),
    )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=extract_error_payload(response))

    response_payload = response.json()
    claims = response_payload.get("claims") if isinstance(response_payload, dict) else None
    if not isinstance(claims, dict):
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "error": "Invalid ticket redeem response"})
    logger.info(
        "Redeemed FMU session ticket request_id=%s session_id=%s lab_id=%s reservation_key=%s ticket_id=%s",
        str(request_id or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(session_id or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(lab_id or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(reservation_key or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(normalize_ticket_id(session_ticket) or "-").replace("\r", "\\r").replace("\n", "\\n"),
    )
    return claims