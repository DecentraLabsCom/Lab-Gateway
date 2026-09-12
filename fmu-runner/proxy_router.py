"""HTTP composition for reservation-scoped FMU proxy downloads.

The router owns only request sequencing and response construction.  Security,
ticket issuance, backend access, and artifact generation are injected so the
application composition root keeps control of deployment-specific behavior.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response


def create_proxy_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_claim_lab_id: Any,
    enforce_requested_reservation: Any,
    allow_proxy_download: Any,
    extract_authorization_header: Any,
    new_request_id: Any,
    issue_session_ticket: Any,
    derive_gateway_ws_url: Any,
    get_authorized_model_metadata: Any,
    build_proxy_model_description_xml: Any,
    parse_fmi_major_version: Any,
    proxy_model_identifier: Any,
    collect_runtime_files: Any,
    build_proxy_session_config: Any,
    build_proxy_artifact: Any,
    build_proxy_artifact_headers: Any,
    normalize_ticket_id: Any,
    get_signing_key: Any,
    logger: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/fmu/proxy/{lab_id}")
    async def download_proxy_fmu(
        lab_id: str,
        request: Request,
        reservationKey: Optional[str] = Query(None),
        claims: dict = Depends(verify_jwt),
    ):
        """Generate and download a reservation-scoped FMU proxy artifact."""
        enforce_fmu_claim(claims)

        claim_lab_id = get_claim_lab_id(claims)
        if claim_lab_id and str(claim_lab_id) != str(lab_id):
            raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")

        claim_reservation_key = str(claims.get("reservationKey") or "").strip()
        enforce_requested_reservation(claims, reservationKey)
        effective_reservation_key = reservationKey or claim_reservation_key
        if not effective_reservation_key:
            raise HTTPException(status_code=400, detail="Missing reservationKey")

        claim_sub = str(claims.get("sub") or "anonymous")
        rate_key = f"{claim_sub}:{lab_id}"
        if not allow_proxy_download(rate_key):
            raise HTTPException(status_code=429, detail="Proxy download rate limit exceeded. Retry shortly.")

        authorization = extract_authorization_header(request)
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing bearer token required to issue session ticket")

        fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
        if not fmu_filename:
            raise HTTPException(status_code=400, detail="Cannot determine FMU file name from token")

        session_ticket, ticket_expiry = await issue_session_ticket(
            authorization,
            lab_id=str(lab_id),
            reservation_key=effective_reservation_key,
            request_id=new_request_id(),
        )
        gateway_ws_url = derive_gateway_ws_url(claims)
        model_metadata = await get_authorized_model_metadata(
            claims=claims,
            requested_fmu_filename=str(fmu_filename),
        )
        model_xml = build_proxy_model_description_xml(model_metadata)
        proxy_fmi_version = (
            "3.0" if parse_fmi_major_version(model_metadata.get("fmiVersion")) >= 3 else "2.0.3"
        )
        proxy_model_identifier_value = proxy_model_identifier(model_metadata)
        runtime_files = collect_runtime_files(
            fmi_version=proxy_fmi_version,
            model_identifier=proxy_model_identifier_value,
        )

        config_payload = build_proxy_session_config(
            fmi_version=proxy_fmi_version,
            gateway_ws_url=gateway_ws_url,
            lab_id=str(lab_id),
            reservation_key=effective_reservation_key,
            session_ticket=session_ticket,
            ticket_expires_at=ticket_expiry,
        )
        archive_bytes = build_proxy_artifact(
            model_xml=model_xml,
            config_payload=config_payload,
            runtime_files=runtime_files,
        )
        signing_key = get_signing_key()
        headers = build_proxy_artifact_headers(
            artifact_bytes=archive_bytes,
            lab_id=str(lab_id),
            signing_key=signing_key,
        )

        logger.info(
            "Generated proxy FMU lab_id=%s reservation_key=%s ticket_id=%s bytes=%s sha256=%s signed=%s",
            str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
            str(effective_reservation_key).replace("\r", "\\r").replace("\n", "\\n"),
            str(normalize_ticket_id(session_ticket) or "-").replace("\r", "\\r").replace("\n", "\\n"),
            len(archive_bytes),
            headers["X-Proxy-Artifact-Sha256"],
            "yes" if signing_key else "no",
        )
        return Response(content=archive_bytes, media_type="application/octet-stream", headers=headers)

    return router
