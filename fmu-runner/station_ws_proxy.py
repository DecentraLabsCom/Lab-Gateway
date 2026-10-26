from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, WebSocket

from station_ws_connection import (
    StationWebSocketConnection,
    _GatewayStationSession,
    _StationWebSocket,
    _cancel_task,
    _normalize_binding,
    _public_http_detail,
)

from simulation_access_policy import (
    AccessDenied,
    validate_reads,
    validate_read_value_references,
    validate_writes,
)

# Must match FMU Executor's bounded per-advance input batch.
MAX_ADVANCE_INPUT_EVENTS = 1024
MAX_ADVANCE_INPUT_BYTES = 256 * 1024
MAX_ADVANCE_OUTPUT_VARIABLES = 512
MAX_ADVANCE_COMPUTE_MS = 1000









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
        issue_session_ticket=None,
        confirm_session_started=None,
        get_effective_policy=None,
        get_session_model_metadata=None,
        get_effective_policy_for_metadata=None,
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
        self.issue_session_ticket = issue_session_ticket
        self.confirm_session_started = confirm_session_started
        self.get_effective_policy = get_effective_policy
        self.get_session_model_metadata = get_session_model_metadata
        self.get_effective_policy_for_metadata = get_effective_policy_for_metadata
        if (get_session_model_metadata is None) != (get_effective_policy_for_metadata is None):
            raise ValueError("Session metadata and metadata-based policy callbacks must be configured together")
        self.ws_cleanup_seconds = ws_cleanup_seconds
        self.internal_ws_token = internal_ws_token
        self.ws_create_rate_limit_per_minute = ws_create_rate_limit_per_minute

        self._sessions: dict[str, _GatewayStationSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._create_hits: dict[str, deque[float]] = defaultdict(deque)

    @property
    def access_policy_enabled(self) -> bool:
        return self.get_effective_policy is not None or self.get_effective_policy_for_metadata is not None

    async def start(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        cleanup_task = self._cleanup_task
        if cleanup_task:
            try:
                await _cancel_task(cleanup_task)
            finally:
                self._cleanup_task = None
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            if session.close_handler:
                try:
                    await session.close_handler()
                except Exception:
                    self.logger.warning(
                        "Unable to close Station session during shutdown session_id=%s",
                        session.session_id,
                        exc_info=True,
                    )

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.ws_cleanup_seconds)
            now = int(time.time())
            async with self._sessions_lock:
                expired = [
                    self._sessions.pop(session_id)
                    for session_id, session in list(self._sessions.items())
                    if session.exp is not None and now >= session.exp
                ]
            for session in expired:
                if session.close_handler:
                    try:
                        await session.close_handler()
                    except Exception:
                        self.logger.warning(
                            "Unable to close expired Station session session_id=%s",
                            session.session_id,
                            exc_info=True,
                        )

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

    async def _refresh_session_access_policy(self, session: _GatewayStationSession) -> Optional[dict]:
        """Refresh an active session's policy before forwarding or exposing FMI data."""
        if not self.access_policy_enabled:
            return session.access_policy
        if self.get_effective_policy_for_metadata is not None and session.model_metadata is not None:
            policy = await self.get_effective_policy_for_metadata(session.claims, session.model_metadata)
        elif self.get_effective_policy is not None:
            policy = await self.get_effective_policy(session.claims)
        else:
            raise RuntimeError("FMU access policy resolver is unavailable")
        if not isinstance(policy, dict) or not isinstance(policy.get("variables"), dict):
            raise RuntimeError("FMU access policy is unavailable")
        session.access_policy = policy
        return policy

    @staticmethod
    def _normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
        if not session_ticket:
            return None
        token = str(session_ticket).strip()
        if token.startswith("st_"):
            token = token[3:]
        return token[:10] if token else None

    @staticmethod
    def _validate_session_message(message: dict, access_policy: dict) -> None:
        """Authorize FMI variable reads/writes before forwarding a command."""
        msg_type = str(message.get("type") or "").strip()
        if msg_type == "sim.initialize":
            parameters = message.get("parameters", {})
            options = message.get("options", {})
            if not isinstance(parameters, dict) or not isinstance(options, dict):
                raise AccessDenied
            validate_writes(access_policy, parameters, phase="initialization")
            if "inputs" in options:
                validate_writes(access_policy, options["inputs"], phase="initialization")
        elif msg_type == "sim.setInputs":
            validate_writes(access_policy, message.get("values", {}), phase="runtime")
        elif msg_type == "sim.advance":
            max_compute_ms = message.get("maxComputeMs")
            if max_compute_ms is not None and (
                isinstance(max_compute_ms, bool)
                or not isinstance(max_compute_ms, (int, float))
                or not math.isfinite(max_compute_ms)
                or not 1 <= max_compute_ms <= MAX_ADVANCE_COMPUTE_MS
            ):
                raise AccessDenied
            input_schedule = message.get("inputSchedule", [])
            if not isinstance(input_schedule, list) or len(input_schedule) > MAX_ADVANCE_INPUT_EVENTS:
                raise AccessDenied
            try:
                schedule_bytes = len(json.dumps(
                    input_schedule,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"))
            except (TypeError, ValueError):
                raise AccessDenied
            if schedule_bytes > MAX_ADVANCE_INPUT_BYTES:
                raise AccessDenied
            for event in input_schedule:
                if not isinstance(event, dict) or not isinstance(event.get("values"), dict):
                    raise AccessDenied
                validate_writes(access_policy, event["values"], phase="runtime")
            if "outputVariables" in message:
                output_variables = message["outputVariables"]
                if not isinstance(output_variables, list) or len(output_variables) > MAX_ADVANCE_OUTPUT_VARIABLES:
                    raise AccessDenied
                validate_reads(access_policy, output_variables)
        elif msg_type in {"sim.getOutputs", "sim.subscribeOutputs"}:
            if "variables" in message and "valueReferences" in message:
                raise AccessDenied
            if "valueReferences" in message:
                validate_read_value_references(access_policy, message["valueReferences"])
            else:
                validate_reads(access_policy, message.get("variables"))

    @classmethod
    def extract_ws_token(cls, websocket: WebSocket) -> str:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:].strip():
            return auth_header[7:].strip()
        raise HTTPException(status_code=401, detail="Missing authentication token")

    @classmethod
    def extract_ws_authorization(cls, websocket: WebSocket) -> str:
        authorization = websocket.headers.get("authorization", "")
        if authorization.startswith("Bearer ") and authorization[7:].strip():
            return f"Bearer {authorization[7:].strip()}"
        raise HTTPException(status_code=401, detail="Missing bearer token")

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

    async def _connect_station(self, headers: dict[str, str]) -> _StationWebSocket:
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
        await StationWebSocketConnection(self).run(websocket, internal=internal)
