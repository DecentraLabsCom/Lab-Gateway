from __future__ import annotations

import asyncio
import inspect
import json
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect


@dataclass
class _GatewayStationSession:
    session_id: str
    claims: dict
    lab_id: Optional[str]
    access_key: str
    exp: Optional[int]

    def matches_claims(self, claims: dict, get_claim_lab_id) -> bool:
        return (
            str(claims.get("sub") or "") == str(self.claims.get("sub") or "")
            and get_claim_lab_id(claims) == self.lab_id
            and str(claims.get("accessKey") or claims.get("fmuFileName") or "") == self.access_key
        )


class StationRealtimeWsProxyManager:
    def __init__(
        self,
        *,
        logger,
        station_backend,
        verify_jwt_token,
        enforce_fmu_claim,
        get_claim_lab_id,
        normalize_lab_id,
        coerce_epoch_seconds,
        redeem_session_ticket=None,
        ws_cleanup_seconds: float = 15.0,
        internal_ws_token: str = "",
        ws_create_rate_limit_per_minute: int = 30,
    ):
        self.logger = logger
        self.station_backend = station_backend
        self.verify_jwt_token = verify_jwt_token
        self.enforce_fmu_claim = enforce_fmu_claim
        self.get_claim_lab_id = get_claim_lab_id
        self.normalize_lab_id = normalize_lab_id
        self.coerce_epoch_seconds = coerce_epoch_seconds
        self.redeem_session_ticket = redeem_session_ticket
        self.ws_cleanup_seconds = ws_cleanup_seconds
        self.internal_ws_token = internal_ws_token
        self.ws_create_rate_limit_per_minute = ws_create_rate_limit_per_minute

        self._sessions: dict[str, _GatewayStationSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._create_hits: dict[str, deque[float]] = defaultdict(deque)

    async def start(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        async with self._sessions_lock:
            self._sessions.clear()

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.ws_cleanup_seconds)
            now = int(time.time())
            async with self._sessions_lock:
                expired = [session_id for session_id, session in self._sessions.items() if session.exp is not None and now >= session.exp]
                for session_id in expired:
                    self._sessions.pop(session_id, None)

    def _allow_session_create(self, key: str) -> bool:
        if self.ws_create_rate_limit_per_minute <= 0:
            return False
        now = time.time()
        bucket = self._create_hits[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= self.ws_create_rate_limit_per_minute:
            return False
        bucket.append(now)
        return True

    @staticmethod
    def _normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
        if not session_ticket:
            return None
        token = str(session_ticket).strip()
        if token.startswith("st_"):
            token = token[3:]
        return token[:10] if token else None

    @staticmethod
    def parse_cookie_header(cookie_header: str) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if not cookie_header:
            return cookies
        for chunk in cookie_header.split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            cookies[name.strip()] = value.strip()
        return cookies

    @classmethod
    def extract_ws_token(cls, websocket: WebSocket) -> str:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        token_param = websocket.query_params.get("token")
        if token_param:
            return token_param
        cookie_header = websocket.headers.get("cookie", "")
        cookies = cls.parse_cookie_header(cookie_header)
        for cookie_name in ("token", "jwt", "jti", "JTI"):
            token = cookies.get(cookie_name)
            if token:
                return token
        raise HTTPException(status_code=401, detail="Missing authentication token")

    @staticmethod
    def error_payload(
        *,
        code: str,
        message: str,
        request_id: Optional[str] = None,
        retryable: bool = False,
        session_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> dict:
        payload = {
            "type": "error",
            "code": code,
            "message": message,
            "retryable": retryable,
        }
        if request_id:
            payload["requestId"] = request_id
        if session_id:
            payload["sessionId"] = session_id
        if details:
            payload["details"] = details
        return payload

    async def _send_json(self, websocket: WebSocket, send_lock: asyncio.Lock, payload: dict):
        async with send_lock:
            await websocket.send_json(payload)

    async def _connect_station(self, headers: dict[str, str]):
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail="websockets dependency is required for FMU_BACKEND_MODE=station",
            ) from exc

        connect_kwargs = {}
        parameters = inspect.signature(websockets.connect).parameters
        if "additional_headers" in parameters:
            connect_kwargs["additional_headers"] = headers
        else:
            connect_kwargs["extra_headers"] = headers
        return await websockets.connect(self.station_backend.station_session_ws_url(), **connect_kwargs)

    async def handle_websocket(self, websocket: WebSocket, *, internal: bool):
        await websocket.accept()
        send_lock = asyncio.Lock()
        local_request_cache: dict[str, dict] = {}
        pending_create_claims: dict[str, dict] = {}
        current_session_id: Optional[str] = None
        station_ws = None
        station_reader_task: Optional[asyncio.Task] = None

        authorization = websocket.headers.get("authorization", "")
        claims: Optional[dict] = None

        async def _close_station():
            nonlocal station_ws, station_reader_task
            if station_reader_task:
                station_reader_task.cancel()
                station_reader_task = None
            if station_ws is not None:
                try:
                    await station_ws.close()
                except Exception:
                    pass
                station_ws = None

        async def _ensure_station():
            nonlocal station_ws, station_reader_task
            if station_ws is not None:
                return
            station_headers = self.station_backend.build_internal_session_headers(authorization=authorization or None)
            station_ws = await self._connect_station(station_headers)
            station_reader_task = asyncio.create_task(_station_reader())

        async def _station_reader():
            nonlocal current_session_id
            try:
                async for raw_message in station_ws:
                    if isinstance(raw_message, bytes):
                        raw_message = raw_message.decode("utf-8")
                    try:
                        payload = json.loads(raw_message)
                    except json.JSONDecodeError:
                        payload = self.error_payload(
                            code="INTERNAL_ERROR",
                            message="Station backend returned invalid websocket payload",
                            retryable=True,
                            session_id=current_session_id,
                        )

                    request_id = str(payload.get("requestId") or "").strip()
                    if request_id:
                        local_request_cache[request_id] = payload

                    msg_type = str(payload.get("type") or "").strip()
                    if msg_type == "session.created":
                        session_id = str(payload.get("sessionId") or "").strip()
                        session_claims = pending_create_claims.pop(request_id, claims or {})
                        if session_id:
                            exp = self.coerce_epoch_seconds(payload.get("expiresAt"))
                            if exp is None:
                                exp = self.coerce_epoch_seconds(session_claims.get("exp"))
                            access_key = str(session_claims.get("accessKey") or session_claims.get("fmuFileName") or "")
                            gateway_session = _GatewayStationSession(
                                session_id=session_id,
                                claims=session_claims,
                                lab_id=self.get_claim_lab_id(session_claims),
                                access_key=access_key,
                                exp=exp,
                            )
                            async with self._sessions_lock:
                                self._sessions[session_id] = gateway_session
                            current_session_id = session_id
                    elif msg_type == "session.attached":
                        session_id = str(payload.get("sessionId") or "").strip()
                        if session_id:
                            current_session_id = session_id
                    elif msg_type == "session.closed":
                        session_id = str(payload.get("sessionId") or "").strip()
                        if session_id:
                            async with self._sessions_lock:
                                self._sessions.pop(session_id, None)
                            if current_session_id == session_id:
                                current_session_id = None

                    await self._send_json(websocket, send_lock, payload)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self.logger.error("Station realtime websocket proxy failed: %s", exc)
                try:
                    await self._send_json(
                        websocket,
                        send_lock,
                        self.error_payload(
                            code="INTERNAL_ERROR",
                            message="Station realtime session channel closed unexpectedly",
                            retryable=True,
                            session_id=current_session_id,
                        ),
                    )
                    await websocket.close(code=1011)
                except Exception:
                    pass

        try:
            if internal and self.internal_ws_token:
                provided = websocket.headers.get("x-internal-session-token", "")
                if not secrets.compare_digest(provided, self.internal_ws_token):
                    await self._send_json(websocket, send_lock, self.error_payload(code="FORBIDDEN", message="Invalid internal token"))
                    await websocket.close(code=1008)
                    return

            try:
                token = self.extract_ws_token(websocket)
                claims = await self.verify_jwt_token(token)
                self.enforce_fmu_claim(claims)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise

            while True:
                raw_message = await websocket.receive_text()
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._send_json(websocket, send_lock, self.error_payload(code="INVALID_COMMAND", message="Invalid JSON payload"))
                    continue

                msg_type = str(message.get("type") or "").strip()
                request_id = str(message.get("requestId") or "").strip()
                if not msg_type:
                    await self._send_json(websocket, send_lock, self.error_payload(code="INVALID_COMMAND", message="Missing message type"))
                    continue
                if not request_id:
                    await self._send_json(websocket, send_lock, self.error_payload(code="INVALID_COMMAND", message="Missing requestId"))
                    continue

                if request_id in local_request_cache:
                    await self._send_json(websocket, send_lock, local_request_cache[request_id])
                    continue

                if msg_type == "session.create":
                    req_lab_id = self.normalize_lab_id(message.get("labId"))
                    reservation_key = self.normalize_lab_id(message.get("reservationKey"))
                    create_claims = claims
                    session_ticket = str(message.get("sessionTicket") or "").strip()
                    client_host = websocket.client.host if websocket.client else "unknown"
                    create_key = (
                        f"sub:{create_claims.get('sub')}:{req_lab_id or '-'}"
                        if create_claims is not None
                        else f"ticket:{self._normalize_ticket_id(session_ticket) or '-'}:{client_host}"
                    )
                    if not self._allow_session_create(create_key):
                        response = self.error_payload(
                            code="RATE_LIMITED",
                            message="Too many session.create requests. Retry shortly.",
                            request_id=request_id,
                            retryable=True,
                        )
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                    if create_claims is None:
                        if not session_ticket:
                            response = self.error_payload(
                                code="UNAUTHORIZED",
                                message="Missing sessionTicket for unauthenticated session.create",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self._send_json(websocket, send_lock, response)
                            local_request_cache[request_id] = response
                            continue
                        if self.redeem_session_ticket is None:
                            response = self.error_payload(
                                code="INTERNAL_ERROR",
                                message="Session ticket redemption is not configured",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self._send_json(websocket, send_lock, response)
                            local_request_cache[request_id] = response
                            continue
                        try:
                            create_claims = await self.redeem_session_ticket(
                                session_ticket=session_ticket,
                                lab_id=req_lab_id,
                                reservation_key=reservation_key,
                                request_id=request_id,
                            )
                            self.enforce_fmu_claim(create_claims)
                            claims = create_claims
                        except HTTPException as exc:
                            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
                            code = detail.get("code")
                            if not code:
                                if exc.status_code == 401:
                                    code = "SESSION_TICKET_INVALID"
                                elif exc.status_code == 403:
                                    code = "FORBIDDEN"
                                else:
                                    code = "INTERNAL_ERROR"
                            response = self.error_payload(
                                code=code,
                                message=detail.get("error") or detail.get("message") or str(exc.detail),
                                request_id=request_id,
                                retryable=exc.status_code >= 500,
                            )
                            self.logger.warning(
                                "station session.create ticket redeem failed request_id=%s lab_id=%s reservation_key=%s ticket_id=%s code=%s",
                                request_id,
                                req_lab_id or "-",
                                reservation_key or "-",
                                self._normalize_ticket_id(session_ticket) or "-",
                                code,
                            )
                            await self._send_json(websocket, send_lock, response)
                            local_request_cache[request_id] = response
                            continue

                    try:
                        self.station_backend.build_authorized_context(
                            claims=create_claims,
                            requested_lab_id=req_lab_id,
                            requested_reservation_key=reservation_key,
                        )
                    except HTTPException as exc:
                        detail_text = str(exc.detail)
                        code = "INTERNAL_ERROR"
                        if exc.status_code == 403:
                            code = "LAB_MISMATCH" if "labId" in detail_text else "FORBIDDEN"
                        response = self.error_payload(
                            code=code,
                            message=detail_text,
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                    try:
                        await _ensure_station()
                        forward_message = self.station_backend.build_internal_session_message(
                            message=message,
                            claims=create_claims,
                            requested_lab_id=req_lab_id,
                            requested_reservation_key=reservation_key,
                        )
                        forward_message.pop("sessionTicket", None)
                        pending_create_claims[request_id] = create_claims
                        await station_ws.send(json.dumps(forward_message))
                        continue
                    except HTTPException as exc:
                        response = self.error_payload(
                            code="INTERNAL_ERROR",
                            message=str(exc.detail),
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                if msg_type == "session.attach":
                    if claims is None:
                        response = self.error_payload(
                            code="UNAUTHORIZED",
                            message="session.attach requires a bearer token",
                            request_id=request_id,
                            retryable=False,
                        )
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                    session_id = str(message.get("sessionId") or "").strip()
                    if not session_id:
                        response = self.error_payload(code="INVALID_COMMAND", message="Missing sessionId", request_id=request_id)
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                    async with self._sessions_lock:
                        session = self._sessions.get(session_id)

                    if not session:
                        response = self.error_payload(code="FORBIDDEN", message="Session not found", request_id=request_id, retryable=False)
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue
                    if session.exp is not None and int(time.time()) >= session.exp:
                        async with self._sessions_lock:
                            self._sessions.pop(session_id, None)
                        response = self.error_payload(code="SESSION_EXPIRED", message="Session has expired", request_id=request_id)
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue
                    if not session.matches_claims(claims, self.get_claim_lab_id):
                        response = self.error_payload(code="FORBIDDEN", message="Session ownership mismatch", request_id=request_id)
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                    try:
                        await _ensure_station()
                        forward_message = self.station_backend.build_internal_session_message(message=message, claims=claims)
                        await station_ws.send(json.dumps(forward_message))
                        continue
                    except HTTPException as exc:
                        response = self.error_payload(
                            code="INTERNAL_ERROR",
                            message=str(exc.detail),
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                        await self._send_json(websocket, send_lock, response)
                        local_request_cache[request_id] = response
                        continue

                if current_session_id is None:
                    response = self.error_payload(code="FORBIDDEN", message="Create or attach a session first", request_id=request_id)
                    await self._send_json(websocket, send_lock, response)
                    local_request_cache[request_id] = response
                    continue

                if station_ws is None:
                    response = self.error_payload(
                        code="INTERNAL_ERROR",
                        message="Station realtime channel is unavailable",
                        request_id=request_id,
                        retryable=True,
                        session_id=current_session_id,
                    )
                    await self._send_json(websocket, send_lock, response)
                    local_request_cache[request_id] = response
                    continue

                await station_ws.send(json.dumps(message))
        except WebSocketDisconnect:
            return
        finally:
            await _close_station()
