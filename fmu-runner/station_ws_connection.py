"""Per-connection state and message forwarding for Station realtime sessions."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol, cast

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from simulation_access_policy import (
    AccessDenied,
    filter_fmi_values,
    filter_model_description,
)


async def _cancel_task(task: Optional[asyncio.Task]) -> None:
    if task is None or task is asyncio.current_task():
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return

class _StationWebSocket(Protocol):
    def __aiter__(self) -> AsyncIterator[str | bytes]:
        raise NotImplementedError

    async def send(self, message: Any, text: bool | None = None) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

def _public_http_detail(exc: Exception, fallback: str) -> str:
    if not isinstance(exc, HTTPException):
        return fallback
    if exc.status_code >= 500:
        return fallback
    if isinstance(exc.detail, dict):
        detail = exc.detail.get("error") or exc.detail.get("message")
    else:
        detail = exc.detail
    return detail if isinstance(detail, str) and len(detail) <= 256 else fallback

def _normalize_binding(value) -> str:
    return str(value or "").strip().lower()


@dataclass
class _GatewayStationSession:
    session_id: str
    claims: dict
    lab_id: Optional[str]
    access_key: str
    exp: Optional[int]
    access_policy: Optional[dict] = None
    model_metadata: Optional[dict] = None
    close_handler: Optional[Callable[[], Awaitable[None]]] = None

    def matches_claims(self, claims: dict, get_claim_lab_id) -> bool:
        return (
            str(claims.get("sub") or "") == str(self.claims.get("sub") or "")
            and get_claim_lab_id(claims) == self.lab_id
            and str(claims.get("accessKey") or claims.get("fmuFileName") or "") == self.access_key
            and _normalize_binding(claims.get("reservationKey")) == _normalize_binding(
                self.claims.get("reservationKey")
            )
            and _normalize_binding(claims.get("pucHash")) == _normalize_binding(
                self.claims.get("pucHash")
            )
            and _normalize_binding(claims.get("targetGatewayId")) == _normalize_binding(
                self.claims.get("targetGatewayId")
            )
        )


class StationWebSocketConnection:
    """Own the per-client WebSocket bridge to the Station session service."""

    def __init__(self, manager: Any):
        self.manager = manager

    async def run(self, websocket: WebSocket, *, internal: bool):
        await websocket.accept()
        send_lock = asyncio.Lock()
        local_request_cache: dict[str, dict] = {}
        response_sizes: dict[str, int] = {}
        response_bytes = 0

        def cache_response(request_id, payload):
            nonlocal response_bytes
            response_bytes -= response_sizes.pop(request_id, 0)
            local_request_cache.pop(request_id, None)
            size = len(json.dumps(payload).encode("utf-8"))
            local_request_cache[request_id] = payload
            response_sizes[request_id] = size
            response_bytes += size
            while len(local_request_cache) > 32 or response_bytes > 2_000_000:
                oldest = next(iter(local_request_cache))
                local_request_cache.pop(oldest)
                response_bytes -= response_sizes.pop(oldest)

        pending_creates: dict[str, dict] = {}
        current_session_id: Optional[str] = None
        station_ws: Optional[_StationWebSocket] = None
        station_reader_task: Optional[asyncio.Task] = None

        authorization = websocket.headers.get("authorization", "")
        claims: Optional[dict] = None
        authorization_deadline = time.monotonic() + 30

        async def _close_station():
            nonlocal station_ws, station_reader_task
            reader_task = station_reader_task
            if reader_task:
                await _cancel_task(reader_task)
                station_reader_task = None
            connection = station_ws
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    # The peer may already have closed the socket.
                    pass
                station_ws = None

        async def _close_expired_session(session_id: str, *, request_id: Optional[str] = None):
            async with self.manager._sessions_lock:
                self.manager._sessions.pop(session_id, None)
            try:
                await self.manager._send_json(
                    websocket,
                    send_lock,
                    self.manager.error_payload(
                        code="SESSION_EXPIRED",
                        message="Session has expired",
                        request_id=request_id,
                        session_id=session_id,
                    ),
                )
            except Exception:
                # The client may already have disconnected; Station still
                # must be closed so its FMU execution cannot outlive exp.
                pass
            finally:
                await _close_station()
            try:
                await websocket.close(code=4003)
            except Exception:
                # The client may already have disconnected; closing is best effort.
                pass

        async def _ensure_station():
            nonlocal station_ws, station_reader_task
            if station_ws is not None:
                return
            station_headers = self.manager.station_backend.build_internal_session_headers(authorization=authorization or None)
            station_ws = await self.manager._connect_station(station_headers)
            station_reader_task = asyncio.create_task(_station_reader())

        async def _send_station(raw_message: str):
            connection = station_ws
            if connection is None:
                raise HTTPException(status_code=503, detail="Station realtime channel is unavailable")
            await connection.send(raw_message)

        async def _station_reader():
            nonlocal current_session_id
            connection = station_ws
            if connection is None:
                return
            try:
                async for raw_message in connection:
                    if isinstance(raw_message, bytes):
                        raw_message = raw_message.decode("utf-8")
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        payload = self.manager.error_payload(
                            code="INTERNAL_ERROR",
                            message="Station backend returned invalid websocket payload",
                            retryable=True,
                            session_id=current_session_id,
                        )

                    request_id = str(payload.get("requestId") or "").strip()

                    msg_type = str(payload.get("type") or "").strip()
                    close_public_on_expiry = False
                    if msg_type == "session.created":
                        session_id = str(payload.get("sessionId") or "").strip()
                        create_context = pending_creates.pop(request_id, {"claims": claims or {}})
                        session_claims = create_context["claims"]
                        if session_id:
                            session_ticket = str(create_context.get("session_ticket") or "").strip()
                            if session_ticket:
                                try:
                                    if self.manager.confirm_session_started is None:
                                        raise HTTPException(status_code=500, detail="Session observation is not configured")
                                    await self.manager.confirm_session_started(
                                        session_ticket=session_ticket,
                                        claims=session_claims,
                                        session_id=session_id,
                                        reservation_key=create_context.get("reservation_key"),
                                        request_id=request_id,
                                    )
                                except Exception as exc:
                                    try:
                                        await connection.send(json.dumps({
                                            "type": "session.terminate",
                                            "requestId": f"observation-failed-{request_id}",
                                            "sessionId": session_id,
                                        }))
                                    except Exception:
                                        # There is no reliable response path after a socket failure.
                                        pass
                                    detail = _public_http_detail(exc, "Session observation failed") if isinstance(exc, HTTPException) else "Session observation failed"
                                    payload = self.manager.error_payload(
                                        code="SESSION_OBSERVATION_FAILED",
                                        message=detail,
                                        request_id=request_id,
                                        retryable=True,
                                        session_id=session_id,
                                    )
                                    if request_id:
                                        cache_response(request_id, payload)
                                    await self.manager._send_json(websocket, send_lock, payload)
                                    continue
                            exp = self.manager.coerce_epoch_seconds(payload.get("expiresAt"))
                            if exp is None:
                                exp = self.manager.coerce_epoch_seconds(session_claims.get("exp"))
                            access_key = str(session_claims.get("accessKey") or session_claims.get("fmuFileName") or "")
                            gateway_session = _GatewayStationSession(
                                session_id=session_id,
                                claims=session_claims,
                                lab_id=self.manager.get_claim_lab_id(session_claims),
                                access_key=access_key,
                                exp=exp,
                                access_policy=create_context.get("access_policy"),
                                model_metadata=create_context.get("model_metadata"),
                            )

                            async def _close_registered_session(session_id=session_id):
                                await _close_expired_session(session_id)

                            gateway_session.close_handler = _close_registered_session
                            async with self.manager._sessions_lock:
                                self.manager._sessions[session_id] = gateway_session
                            current_session_id = session_id
                    elif msg_type == "session.attached":
                        session_id = str(payload.get("sessionId") or "").strip()
                        if session_id:
                            current_session_id = session_id
                    elif msg_type == "session.closed":
                        session_id = str(payload.get("sessionId") or "").strip()
                        if session_id:
                            async with self.manager._sessions_lock:
                                self.manager._sessions.pop(session_id, None)
                            if current_session_id == session_id:
                                current_session_id = None
                        if str(payload.get("reason") or "").strip().lower() == "expired":
                            close_public_on_expiry = True

                    policy_session_id = str(payload.get("sessionId") or current_session_id or "").strip()
                    if policy_session_id:
                        async with self.manager._sessions_lock:
                            policy_session = self.manager._sessions.get(policy_session_id)
                        try:
                            access_policy = (
                                await self.manager._refresh_session_access_policy(policy_session)
                                if policy_session is not None
                                else None
                            )
                        except Exception:
                            payload = self.manager.error_payload(
                                code="ACCESS_POLICY_UNAVAILABLE",
                                message="Unable to refresh the FMU access policy",
                                request_id=request_id,
                                retryable=True,
                                session_id=policy_session_id,
                            )
                            if request_id:
                                cache_response(request_id, payload)
                            await self.manager._send_json(websocket, send_lock, payload)
                            continue
                        if access_policy is not None:
                            if msg_type == "model.description":
                                payload = filter_model_description(access_policy, payload)
                            else:
                                payload = filter_fmi_values(access_policy, payload)

                    if request_id:
                        cache_response(request_id, payload)
                    await self.manager._send_json(websocket, send_lock, payload)
                    if close_public_on_expiry:
                        try:
                            await websocket.close(code=4003)
                        except Exception:
                            # The client may already have disconnected; closing is best effort.
                            pass
                        return
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self.manager.logger.error("Station realtime websocket proxy failed: %s", exc)
                try:
                    await self.manager._send_json(
                        websocket,
                        send_lock,
                        self.manager.error_payload(
                            code="INTERNAL_ERROR",
                            message="Station realtime session channel closed unexpectedly",
                            retryable=True,
                            session_id=current_session_id,
                        ),
                    )
                    await websocket.close(code=1011)
                except Exception:
                    # Closing an already-closed client websocket is harmless.
                    pass

        try:
            if internal:
                if not self.manager.internal_ws_token:
                    await self.manager._send_json(
                        websocket,
                        send_lock,
                        self.manager.error_payload(code="FORBIDDEN", message="Internal token is not configured"),
                    )
                    await websocket.close(code=1008)
                    return
                provided = websocket.headers.get("x-internal-session-token", "")
                if not secrets.compare_digest(provided, self.manager.internal_ws_token):
                    await self.manager._send_json(websocket, send_lock, self.manager.error_payload(code="FORBIDDEN", message="Invalid internal token"))
                    await websocket.close(code=1008)
                    return

            try:
                token = self.manager.extract_ws_token(websocket)
                claims = await self.manager.verify_jwt_token(token)
                self.manager.enforce_fmu_claim(claims)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise

            while True:
                try:
                    raw_message = await asyncio.wait_for(websocket.receive_text(), timeout=max(0.001, authorization_deadline - time.monotonic()) if claims is None else None)
                except asyncio.TimeoutError:
                    await websocket.close(code=1008)
                    return
                if len(raw_message) > 1_000_000:
                    await websocket.close(code=1009)
                    return
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self.manager._send_json(websocket, send_lock, self.manager.error_payload(code="INVALID_COMMAND", message="Invalid JSON payload"))
                    continue

                if not isinstance(message, dict):
                    await websocket.close(code=1008)
                    return
                msg_type = str(message.get("type") or "").strip()
                request_id = str(message.get("requestId") or "").strip()
                if not msg_type:
                    await self.manager._send_json(websocket, send_lock, self.manager.error_payload(code="INVALID_COMMAND", message="Missing message type"))
                    continue
                if not request_id:
                    await self.manager._send_json(websocket, send_lock, self.manager.error_payload(code="INVALID_COMMAND", message="Missing requestId"))
                    continue

                if request_id in local_request_cache:
                    await self.manager._send_json(websocket, send_lock, local_request_cache[request_id])
                    continue

                if msg_type == "session.create":
                    req_lab_id = self.manager.normalize_lab_id(message.get("labId"))
                    reservation_key = self.manager.normalize_lab_id(message.get("reservationKey"))
                    create_claims = claims
                    session_ticket = str(message.get("sessionTicket") or "").strip()
                    client_host = websocket.client.host if websocket.client else "unknown"
                    create_key = (
                        f"sub:{create_claims.get('sub')}:{req_lab_id or '-'}"
                        if create_claims is not None
                        else f"anonymous:{client_host}"
                    )
                    if not self.manager._allow_session_create(create_key):
                        response = self.manager.error_payload(
                            code="RATE_LIMITED",
                            message="Too many session.create requests. Retry shortly.",
                            request_id=request_id,
                            retryable=True,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                    if create_claims is None:
                        if not session_ticket:
                            response = self.manager.error_payload(
                                code="UNAUTHORIZED",
                                message="Missing sessionTicket for unauthenticated session.create",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue

                    if not internal and not session_ticket:
                        authenticated_claims = cast(dict[str, Any], create_claims)
                        claim_lab_id = self.manager.get_claim_lab_id(authenticated_claims)
                        if claim_lab_id and req_lab_id and claim_lab_id != req_lab_id:
                            response = self.manager.error_payload(
                                code="LAB_MISMATCH",
                                message="JWT not authorised for requested labId",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        claim_reservation_key = str(authenticated_claims.get("reservationKey") or "").strip()
                        if reservation_key and claim_reservation_key and reservation_key.lower() != claim_reservation_key.lower():
                            response = self.manager.error_payload(
                                code="FORBIDDEN",
                                message="JWT not authorised for requested reservationKey",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        if not (authenticated_claims.get("accessKey") or authenticated_claims.get("fmuFileName")):
                            response = self.manager.error_payload(
                                code="FORBIDDEN",
                                message="Token has no authorised FMU file",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        if self.manager.issue_session_ticket is None:
                            response = self.manager.error_payload(
                                code="INTERNAL_ERROR",
                                message="Session ticket issuance is not configured",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        try:
                            session_ticket, _ticket_expiry = await self.manager.issue_session_ticket(
                                authorization=self.manager.extract_ws_authorization(websocket),
                                lab_id=req_lab_id or self.manager.get_claim_lab_id(authenticated_claims),
                                reservation_key=reservation_key or authenticated_claims.get("reservationKey"),
                                request_id=request_id,
                            )
                            session_ticket = str(session_ticket or "").strip()
                            if not session_ticket:
                                raise HTTPException(status_code=500, detail="Session ticket issuance returned no ticket")
                        except HTTPException as exc:
                            detail = exc.detail if isinstance(exc.detail, dict) else {}
                            response = self.manager.error_payload(
                                code=detail.get("code") or ("FORBIDDEN" if exc.status_code == 403 else "INTERNAL_ERROR"),
                                message=_public_http_detail(exc, "Unable to issue session ticket"),
                                request_id=request_id,
                                retryable=exc.status_code >= 500,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        except Exception as exc:
                            response = self.manager.error_payload(
                                code="INTERNAL_ERROR",
                                message="Unable to issue session ticket",
                                request_id=request_id,
                                retryable=True,
                            )
                            self.manager.logger.warning(
                                "station session.create ticket issue failed request_id=%s error=%s",
                                str(request_id).replace("\r", "\\r").replace("\n", "\\n"),
                                type(exc).__name__,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue

                    if not internal and session_ticket:
                        if self.manager.redeem_session_ticket is None:
                            response = self.manager.error_payload(
                                code="INTERNAL_ERROR",
                                message="Session ticket redemption is not configured",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        try:
                            create_claims = await self.manager.redeem_session_ticket(
                                session_ticket=session_ticket,
                                lab_id=req_lab_id,
                                reservation_key=reservation_key,
                                request_id=request_id,
                            )
                            self.manager.enforce_fmu_claim(create_claims)
                            claims = create_claims
                        except HTTPException as exc:
                            detail = exc.detail if isinstance(exc.detail, dict) else {}
                            code = detail.get("code") or ("SESSION_TICKET_INVALID" if exc.status_code == 401 else ("FORBIDDEN" if exc.status_code == 403 else "INTERNAL_ERROR"))
                            response = self.manager.error_payload(
                                code=code,
                                message=_public_http_detail(exc, "Unable to redeem session ticket"),
                                request_id=request_id,
                                retryable=exc.status_code >= 500,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        except Exception:
                            response = self.manager.error_payload(
                                code="SESSION_TICKET_INVALID",
                                message="Unable to redeem session ticket",
                                request_id=request_id,
                                retryable=True,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                    try:
                        self.manager.station_backend.build_authorized_context(
                            claims=create_claims,
                            requested_lab_id=req_lab_id,
                            requested_reservation_key=reservation_key,
                        )
                    except HTTPException as exc:
                        detail_text = _public_http_detail(exc, "Unable to authorize station session")
                        code = "INTERNAL_ERROR"
                        if exc.status_code == 403:
                            code = "LAB_MISMATCH" if "labId" in detail_text else "FORBIDDEN"
                        response = self.manager.error_payload(
                            code=code,
                            message=detail_text,
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                    access_policy = None
                    model_metadata = None
                    if self.manager.access_policy_enabled:
                        try:
                            if (
                                self.manager.get_session_model_metadata is not None
                                and self.manager.get_effective_policy_for_metadata is not None
                            ):
                                model_metadata = await self.manager.get_session_model_metadata(create_claims)
                                if (
                                    not isinstance(model_metadata, dict)
                                    or not isinstance(model_metadata.get("modelVariables"), list)
                                ):
                                    raise HTTPException(status_code=503, detail="FMU model metadata is unavailable")
                                access_policy = await self.manager.get_effective_policy_for_metadata(
                                    create_claims,
                                    model_metadata,
                                )
                            elif self.manager.get_effective_policy is not None:
                                access_policy = await self.manager.get_effective_policy(create_claims)
                            else:
                                raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
                            if not isinstance(access_policy, dict) or not isinstance(access_policy.get("variables"), dict):
                                raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
                            self.manager._validate_session_message(message, access_policy)
                        except AccessDenied:
                            response = self.manager.error_payload(
                                code="VARIABLE_ACCESS_DENIED",
                                message="Variable access denied by the effective FMU policy",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue
                        except Exception as exc:
                            if isinstance(exc, HTTPException):
                                if exc.status_code < 500:
                                    error_message = _public_http_detail(exc, "Not authorized")
                                    error_code = "FORBIDDEN"
                                    retryable = False
                                else:
                                    error_message = "Unable to resolve FMU access policy"
                                    error_code = "ACCESS_POLICY_UNAVAILABLE"
                                    retryable = True
                            else:
                                error_message = "Unable to resolve FMU access policy"
                                error_code = "ACCESS_POLICY_UNAVAILABLE"
                                retryable = True
                            response = self.manager.error_payload(
                                code=error_code,
                                message=error_message,
                                request_id=request_id,
                                retryable=retryable,
                            )
                            await self.manager._send_json(websocket, send_lock, response)
                            cache_response(request_id, response)
                            continue

                    try:
                        await _ensure_station()
                        forward_message = self.manager.station_backend.build_internal_session_message(
                            message=message,
                            claims=create_claims,
                            requested_lab_id=req_lab_id,
                            requested_reservation_key=reservation_key,
                        )
                        forward_message.pop("sessionTicket", None)
                        pending_creates[request_id] = {
                            "claims": create_claims,
                            "session_ticket": session_ticket,
                            "reservation_key": reservation_key,
                            "access_policy": access_policy,
                            "model_metadata": model_metadata,
                        }
                        await _send_station(json.dumps(forward_message))
                        continue
                    except HTTPException as exc:
                        response = self.manager.error_payload(
                            code="INTERNAL_ERROR",
                            message=_public_http_detail(exc, "Station realtime channel unavailable"),
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                if msg_type == "session.attach":
                    if claims is None:
                        response = self.manager.error_payload(
                            code="UNAUTHORIZED",
                            message="session.attach requires a bearer token",
                            request_id=request_id,
                            retryable=False,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                    session_id = str(message.get("sessionId") or "").strip()
                    if not session_id:
                        response = self.manager.error_payload(code="INVALID_COMMAND", message="Missing sessionId", request_id=request_id)
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                    async with self.manager._sessions_lock:
                        session = self.manager._sessions.get(session_id)

                    if not session:
                        response = self.manager.error_payload(code="FORBIDDEN", message="Session not found", request_id=request_id, retryable=False)
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue
                    if session.exp is not None and int(time.time()) >= session.exp:
                        await _close_expired_session(session_id, request_id=request_id)
                        return
                    if not session.matches_claims(claims, self.manager.get_claim_lab_id):
                        response = self.manager.error_payload(code="FORBIDDEN", message="Session ownership mismatch", request_id=request_id)
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                    try:
                        await _ensure_station()
                        forward_message = self.manager.station_backend.build_internal_session_message(message=message, claims=claims)
                        await _send_station(json.dumps(forward_message))
                        continue
                    except HTTPException as exc:
                        response = self.manager.error_payload(
                            code="INTERNAL_ERROR",
                            message=_public_http_detail(exc, "Station realtime channel unavailable"),
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                if current_session_id is None:
                    response = self.manager.error_payload(code="FORBIDDEN", message="Create or attach a session first", request_id=request_id)
                    await self.manager._send_json(websocket, send_lock, response)
                    cache_response(request_id, response)
                    continue

                if station_ws is None:
                    response = self.manager.error_payload(
                        code="INTERNAL_ERROR",
                        message="Station realtime channel is unavailable",
                        request_id=request_id,
                        retryable=True,
                        session_id=current_session_id,
                    )
                    await self.manager._send_json(websocket, send_lock, response)
                    cache_response(request_id, response)
                    continue

                async with self.manager._sessions_lock:
                    active_session = self.manager._sessions.get(current_session_id)
                if self.manager.access_policy_enabled and active_session is None:
                    response = self.manager.error_payload(
                        code="FORBIDDEN",
                        message="Session is no longer available",
                        request_id=request_id,
                        retryable=False,
                        session_id=current_session_id,
                    )
                    await self.manager._send_json(websocket, send_lock, response)
                    cache_response(request_id, response)
                    continue
                if active_session and active_session.exp is not None and int(time.time()) >= active_session.exp:
                    await _close_expired_session(current_session_id, request_id=request_id)
                    return

                if active_session and self.manager.access_policy_enabled:
                    try:
                        await self.manager._refresh_session_access_policy(active_session)
                    except Exception:
                        response = self.manager.error_payload(
                            code="ACCESS_POLICY_UNAVAILABLE",
                            message="Unable to refresh the FMU access policy",
                            request_id=request_id,
                            retryable=True,
                            session_id=current_session_id,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                if active_session and active_session.access_policy is not None:
                    try:
                        self.manager._validate_session_message(message, active_session.access_policy)
                    except AccessDenied:
                        response = self.manager.error_payload(
                            code="VARIABLE_ACCESS_DENIED",
                            message="Variable access denied by the effective FMU policy",
                            request_id=request_id,
                            retryable=False,
                            session_id=current_session_id,
                        )
                        await self.manager._send_json(websocket, send_lock, response)
                        cache_response(request_id, response)
                        continue

                await _send_station(json.dumps(message))
        except WebSocketDisconnect:
            return
        finally:
            await _close_station()
