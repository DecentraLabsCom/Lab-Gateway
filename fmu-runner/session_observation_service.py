from typing import Any, Optional

import httpx
from fastapi import HTTPException


async def confirm_session_started(
    *,
    session_ticket: str,
    claims: dict,
    session_id: str,
    reservation_key: Optional[str] = None,
    request_id: Optional[str] = None,
    audit_url: str,
    build_payload: Any,
    post_observation: Any,
    observer_authorization: Any,
    extract_error_payload: Any,
    observed_at: Any,
    normalize_ticket_id: Any,
    logger: Any,
) -> bool:
    claim_reservation_key = str(claims.get("reservationKey") or "").strip()
    if not claim_reservation_key:
        raise HTTPException(status_code=403, detail="Redeemed FMU ticket has no reservationKey")
    if reservation_key and claim_reservation_key.lower() != str(reservation_key).strip().lower():
        raise HTTPException(status_code=403, detail="Redeemed FMU ticket reservation mismatch")
    if not audit_url:
        raise HTTPException(
            status_code=503,
            detail={"code": "SESSION_OBSERVATION_UNAVAILABLE", "error": "ACCESS_AUDIT_URL is not configured"},
        )

    body = build_payload(
        session_ticket=session_ticket,
        reservation_key=claim_reservation_key,
        session_id=session_id,
        observed_at=observed_at(),
    )
    response = await post_observation(
        audit_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": observer_authorization(),
        },
        json=body,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=extract_error_payload(response))
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("recorded") is not True:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SESSION_OBSERVATION_FAILED",
                "error": "Session observation was not durably recorded",
                "auditRecorded": payload.get("auditRecorded") if isinstance(payload, dict) else False,
                "attestationRecorded": payload.get("attestationRecorded") if isinstance(payload, dict) else False,
            },
        )
    logger.info(
        "Confirmed FMU session request_id=%s session_id=%s reservation_key=%s ticket_id=%s",
        str(request_id or "-").replace("\r", "\\r").replace("\n", "\\n"),
        str(session_id).replace("\r", "\\r").replace("\n", "\\n"),
        str(claim_reservation_key).replace("\r", "\\r").replace("\n", "\\n"),
        str(normalize_ticket_id(session_ticket) or "-").replace("\r", "\\r").replace("\n", "\\n"),
    )
    return True


async def confirm_session_started_with_retries(
    *,
    confirm_session: Any,
    session_ticket: str,
    claims: dict,
    reservation_key: Optional[str],
    session_id: str,
    request_id: Optional[str] = None,
    max_attempts: int,
    sleep: Any,
) -> bool:
    for attempt in range(max_attempts):
        try:
            return await confirm_session(
                session_ticket=session_ticket,
                claims=claims,
                reservation_key=reservation_key,
                session_id=session_id,
                request_id=request_id,
            )
        except HTTPException as exc:
            if exc.status_code < 500 or attempt + 1 >= max_attempts:
                raise
            await sleep(0.2 * (2 ** attempt))
        except httpx.HTTPError:
            if attempt + 1 >= max_attempts:
                raise
            await sleep(0.2 * (2 ** attempt))
    raise RuntimeError("session observation retry policy exhausted without an attempt")


async def record_browser_session_started(
    request: Any,
    claims: dict,
    sim_id: str,
    *,
    observation_lock: Any,
    observed_credentials: Any,
    extract_authorization: Any,
    issue_session_ticket: Any,
    redeem_session_ticket: Any,
    retry_confirmation: Any,
    confirm_session: Any,
    max_attempts: int,
    sleep: Any,
) -> bool:
    puc_hash = str(claims.get("pucHash") or "").strip().lower()
    reservation_key = str(claims.get("reservationKey") or "").strip().lower()
    if not puc_hash or not reservation_key:
        raise HTTPException(status_code=403, detail="Missing credential identity for session observation")
    observation_key = f"{reservation_key}:{puc_hash}"
    with observation_lock:
        if observation_key in observed_credentials:
            return False

    authorization = extract_authorization(request)
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing bearer token required for session observation")

    lab_id = str(claims.get("labId") or "").strip()
    session_id = f"fmu:{sim_id}"
    request_id = f"browser_{sim_id[:12]}"
    ticket, _expires_at = await issue_session_ticket(
        authorization,
        lab_id=lab_id,
        reservation_key=reservation_key,
        request_id=request_id,
    )
    redeemed_claims = await redeem_session_ticket(
        session_ticket=ticket,
        lab_id=lab_id,
        reservation_key=reservation_key,
        session_id=session_id,
        request_id=request_id,
    )
    await retry_confirmation(
        confirm_session=confirm_session,
        session_ticket=ticket,
        claims=redeemed_claims,
        reservation_key=reservation_key,
        session_id=session_id,
        request_id=request_id,
        max_attempts=max_attempts,
        sleep=sleep,
    )
    with observation_lock:
        observed_credentials.add(observation_key)
    return True