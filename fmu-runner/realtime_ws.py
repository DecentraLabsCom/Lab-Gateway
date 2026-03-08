import asyncio
import json
import secrets
import shutil
import time
from collections import defaultdict
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fmpy import extract, instantiate_fmu, read_model_description


@dataclass
class _StreamSubscription:
    variables: Optional[list[str]] = None
    period_ms: int = 100
    max_batch_size: int = 64
    max_hz: Optional[float] = None
    last_emit_monotonic: float = 0.0
    rate_dropped: int = 0

    def min_interval_seconds(self) -> float:
        period_interval = max(1, self.period_ms) / 1000.0
        hz_interval = 0.0
        if self.max_hz is not None and self.max_hz > 0:
            hz_interval = 1.0 / self.max_hz
        return max(period_interval, hz_interval)


@dataclass
class _WsConnection:
    websocket: WebSocket
    queue_size: int
    queue: asyncio.Queue = field(init=False)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    sender_task: Optional[asyncio.Task] = None
    attached_at: float = field(default_factory=time.time)

    def __post_init__(self):
        self.queue = asyncio.Queue(maxsize=self.queue_size)


class _RealtimeSession:
    def __init__(self, manager: "RealtimeWsManager", session_id: str, claims: dict, fmu_path: Path):
        self.manager = manager
        self.session_id = session_id
        self.sub = str(claims.get("sub") or "")
        self.lab_id = manager.get_claim_lab_id(claims) or "unknown"
        self.access_key = str(claims.get("accessKey") or claims.get("fmuFileName") or "")
        self.nbf = manager.coerce_epoch_seconds(claims.get("nbf"))
        self.exp = manager.coerce_epoch_seconds(claims.get("exp"))
        self.fmu_path = fmu_path
        self.state = "created"
        self.current_time = 0.0
        self.stop_time = 1.0
        self.step_size = 0.01
        self.connection: Optional[_WsConnection] = None
        self.attach_deadline: Optional[float] = None
        self.subscription: Optional[_StreamSubscription] = None
        self.seq = 0
        self._pending_queue_drops = 0
        self._request_cache: dict[str, dict] = {}
        self._request_cache_order: list[str] = []
        self._runner_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._closed = False
        self._model_description = None
        self._model_payload: Optional[dict] = None
        self._variables: dict[str, Any] = {}
        self._variables_by_value_reference: dict[int, Any] = {}
        self._fmu = None
        self._unzipdir: Optional[str] = None
        self._last_expiry_notice = 0
        self._pending_samples: list[dict[str, Any]] = []
        self.capabilities = {
            "pause": True,
            "reset": True,
            "step": True,
            "setInputs": True,
            "streamOutputs": True,
            "modelDescribe": True,
            "getState": True,
            "attach": True,
        }

    def is_closed(self) -> bool:
        return self._closed

    def matches_claims(self, claims: dict) -> bool:
        return str(claims.get("sub") or "") == self.sub and self.manager.get_claim_lab_id(claims) == self.lab_id and (
            str(claims.get("accessKey") or claims.get("fmuFileName") or "") == self.access_key
        )

    def ensure_reservation_window(self):
        now = int(time.time())
        if self.nbf is not None and now < self.nbf:
            raise HTTPException(status_code=403, detail="Reservation is not active yet")
        if self.exp is not None and now >= self.exp:
            raise HTTPException(status_code=401, detail="Reservation token has expired")

    async def attach(self, connection: _WsConnection):
        self.attach_deadline = None
        if self.connection and self.connection is not connection and self.connection.sender_task:
            self.connection.sender_task.cancel()
        self.connection = connection
        connection.sender_task = asyncio.create_task(self._sender_loop(connection))
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def detach(self):
        if self.connection and self.connection.sender_task:
            self.connection.sender_task.cancel()
        self.connection = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        self.attach_deadline = time.time() + self.manager.ws_attach_grace_seconds

    def cache_response(self, request_id: str, payload: dict):
        self._request_cache[request_id] = payload
        self._request_cache_order.append(request_id)
        while len(self._request_cache_order) > 256:
            stale = self._request_cache_order.pop(0)
            self._request_cache.pop(stale, None)

    def get_cached(self, request_id: str) -> Optional[dict]:
        return self._request_cache.get(request_id)

    async def _sender_loop(self, connection: _WsConnection):
        try:
            while True:
                payload = await connection.queue.get()
                async with connection.send_lock:
                    await connection.websocket.send_json(payload)
        except Exception:
            return

    async def _enqueue_event(self, payload: dict):
        if not self.connection:
            return
        queue = self.connection.queue
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                _ = queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._pending_queue_drops += 1
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                self._pending_queue_drops += 1

    async def _heartbeat_loop(self):
        try:
            while True:
                await asyncio.sleep(self.manager.ws_heartbeat_seconds)
                if self.is_closed():
                    return
                await self._enqueue_event({
                    "type": "session.heartbeat",
                    "sessionId": self.session_id,
                    "serverTime": int(time.time()),
                    "state": self.state,
                    "simTime": self.current_time,
                })
                if self.exp is not None:
                    remaining = self.exp - int(time.time())
                    if 0 < remaining <= self.manager.ws_expiring_notice_seconds and remaining != self._last_expiry_notice:
                        self._last_expiry_notice = remaining
                        await self._enqueue_event({
                            "type": "session.expiring",
                            "sessionId": self.session_id,
                            "expiresAt": self.exp,
                            "secondsRemaining": remaining,
                        })
        except asyncio.CancelledError:
            return

    def _ensure_model_loaded(self):
        if self._model_description is not None:
            return
        md = read_model_description(str(self.fmu_path))
        self._model_description = md
        self._model_payload = self.manager.model_description_payload(md)
        self._variables = {var.name: var for var in md.modelVariables}
        self._variables_by_value_reference = {int(var.valueReference): var for var in md.modelVariables}

    @staticmethod
    def _coerce_dimension_extent_value(value: Any) -> int:
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise HTTPException(status_code=400, detail="Dimension extent must resolve to a single scalar value")
            value = value[0]
        try:
            extent = int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid FMU dimension extent: {value}") from None
        if extent < 0:
            raise HTTPException(status_code=400, detail=f"Invalid negative FMU dimension extent: {extent}")
        return extent

    def _resolve_dimension_extent(self, dimension: Any) -> int:
        if getattr(dimension, "start", None) is not None:
            return self._coerce_dimension_extent_value(dimension.start)
        if getattr(dimension, "valueReference", None) is not None:
            referenced = self._variables_by_value_reference.get(int(dimension.valueReference))
            if referenced is None:
                raise HTTPException(status_code=400, detail="Dimension references an unknown FMU variable")
            if getattr(referenced, "start", None) is not None:
                return self._coerce_dimension_extent_value(referenced.start)
            getter_name = f"get{referenced.type}"
            getter = getattr(self._fmu, getter_name, None) if self._fmu is not None else None
            if getter is not None:
                values = getter([int(referenced.valueReference)])
                if values:
                    return self._coerce_dimension_extent_value(values[0])
        if getattr(dimension, "variable", None) is not None and getattr(dimension.variable, "start", None) is not None:
            return self._coerce_dimension_extent_value(dimension.variable.start)
        raise HTTPException(status_code=400, detail="Unable to resolve FMU dimension extent")

    def _variable_flat_size(self, variable: Any) -> int:
        dimensions = getattr(variable, "dimensions", None) or []
        if not dimensions:
            return 1
        size = 1
        for dimension in dimensions:
            size *= self._resolve_dimension_extent(dimension)
        return size

    @staticmethod
    def _normalize_variable_type(variable: Any) -> str:
        variable_type = str(variable.type)
        if variable_type == "Enumeration":
            return "Integer"
        return variable_type

    @staticmethod
    def _normalize_scalar_value(variable_type: str, value: Any) -> Any:
        if variable_type in ("Real", "Float32", "Float64"):
            return float(value)
        if variable_type in ("Integer", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"):
            return int(value)
        if variable_type == "Boolean":
            return bool(value)
        if variable_type == "String":
            return value.decode("utf-8") if isinstance(value, bytes) else str(value)
        raise HTTPException(status_code=400, detail=f"Realtime sessions do not support FMU variable type {variable_type}")

    def _set_values(self, values: dict[str, Any]):
        if not self._fmu:
            raise HTTPException(status_code=409, detail="Simulation is not initialized")
        by_type: dict[str, dict[str, list[Any]]] = defaultdict(lambda: {"refs": [], "values": []})
        for name, value in values.items():
            variable = self._variables.get(name)
            if not variable:
                continue
            variable_type = self._normalize_variable_type(variable)
            variable_size = self._variable_flat_size(variable)
            if variable_size > 1:
                if not isinstance(value, (list, tuple)):
                    raise HTTPException(status_code=400, detail=f"Array input '{name}' must be provided as a JSON array")
                if len(value) != variable_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Array input '{name}' expects {variable_size} values but received {len(value)}",
                    )
                by_type[variable_type]["refs"].append(int(variable.valueReference))
                by_type[variable_type]["values"].extend(list(value))
            else:
                by_type[variable_type]["refs"].append(int(variable.valueReference))
                by_type[variable_type]["values"].append(value)

        for variable_type, payload in by_type.items():
            refs = payload["refs"]
            vals = payload["values"]
            setter_name = f"set{variable_type}"
            setter = getattr(self._fmu, setter_name, None)
            if setter is None:
                raise HTTPException(status_code=400, detail=f"Realtime sessions do not support FMU variable type {variable_type}")
            if variable_type in ("Real", "Float32", "Float64"):
                setter(list(refs), [float(v) for v in vals])
            elif variable_type in ("Integer", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"):
                setter(list(refs), [int(v) for v in vals])
            elif variable_type == "Boolean":
                setter(list(refs), [bool(v) for v in vals])
            elif variable_type == "String":
                setter(list(refs), [str(v) for v in vals])
            else:
                raise HTTPException(status_code=400, detail=f"Realtime sessions do not support FMU variable type {variable_type}")

    def _get_values(self, variables: list[str]) -> dict[str, Any]:
        if not self._fmu:
            raise HTTPException(status_code=409, detail="Simulation is not initialized")
        selected: list[Any] = []
        for name in variables:
            var = self._variables.get(name)
            if var is not None:
                selected.append(var)

        by_type: dict[str, dict[str, Any]] = defaultdict(lambda: {"variables": [], "refs": [], "nValues": 0})
        for var in selected:
            variable_type = self._normalize_variable_type(var)
            by_type[variable_type]["variables"].append(var)
            by_type[variable_type]["refs"].append(int(var.valueReference))
            by_type[variable_type]["nValues"] += self._variable_flat_size(var)

        outputs: dict[str, Any] = {}
        for variable_type, payload in by_type.items():
            typed_variables = payload["variables"]
            refs = payload["refs"]
            getter_name = f"get{variable_type}"
            getter = getattr(self._fmu, getter_name, None)
            if getter is None:
                raise HTTPException(status_code=400, detail=f"Realtime sessions do not support FMU variable type {variable_type}")
            if payload["nValues"] != len(refs):
                vals = getter(list(refs), nValues=payload["nValues"])
            else:
                vals = getter(list(refs))
            offset = 0
            for variable in typed_variables:
                value_count = self._variable_flat_size(variable)
                raw_segment = vals[offset: offset + value_count]
                offset += value_count
                normalized_segment = [self._normalize_scalar_value(variable_type, value) for value in raw_segment]
                outputs[variable.name] = normalized_segment[0] if value_count == 1 else normalized_segment
        return outputs

    def _default_output_variables(self) -> list[str]:
        names = []
        for var in self._variables.values():
            causality = (var.causality or "").lower()
            if causality in ("output", "local"):
                names.append(var.name)
        if not names:
            names = [var.name for var in self._variables.values()]
        return names

    def _sample_outputs(self) -> dict[str, Any]:
        variables = self.subscription.variables if self.subscription and self.subscription.variables else self._default_output_variables()
        return self._get_values(variables)

    async def _emit_outputs_if_needed(self, force: bool = False):
        if not self.subscription:
            return
        self._pending_samples.append(self._sample_outputs())
        if len(self._pending_samples) > self.subscription.max_batch_size:
            dropped_samples = len(self._pending_samples) - self.subscription.max_batch_size
            self._pending_samples = self._pending_samples[dropped_samples:]
            self.subscription.rate_dropped += dropped_samples

        now_mono = time.monotonic()
        min_interval = self.subscription.min_interval_seconds()
        if not force and (now_mono - self.subscription.last_emit_monotonic) < min_interval:
            self.subscription.rate_dropped += 1
            return
        self.subscription.last_emit_monotonic = now_mono
        values = self._pending_samples[-1]
        batch_size = len(self._pending_samples)
        self._pending_samples.clear()
        dropped = self.subscription.rate_dropped + self._pending_queue_drops
        self.subscription.rate_dropped = 0
        self._pending_queue_drops = 0
        payload = {
            "type": "sim.outputs",
            "sessionId": self.session_id,
            "seq": self.seq,
            "dropped": dropped,
            "batchSize": batch_size,
            "simTime": self.current_time,
            "values": values,
        }
        self.seq += 1
        await self._enqueue_event(payload)

    async def _emit_state(self):
        await self._enqueue_event({
            "type": "sim.state",
            "sessionId": self.session_id,
            "state": self.state,
            "simTime": self.current_time,
        })

    def _shutdown_fmu(self):
        if self._fmu is not None:
            try:
                self._fmu.terminate()
            except Exception:
                pass
            try:
                self._fmu.freeInstance()
            except Exception:
                pass
        self._fmu = None
        if self._unzipdir:
            try:
                shutil.rmtree(self._unzipdir, ignore_errors=True)
            except Exception:
                pass
            self._unzipdir = None

    async def initialize(self, options: dict):
        self.ensure_reservation_window()
        self._ensure_model_loaded()
        if self._model_payload and self._model_payload.get("simulationKind") != "coSimulation":
            raise HTTPException(status_code=400, detail="Realtime sessions currently support only coSimulation FMUs")
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
        self._runner_task = None

        self.current_time = self.manager.coerce_float(options.get("startTime"), 0.0)
        self.stop_time = self.manager.coerce_float(options.get("stopTime"), 10.0)
        self.step_size = self.manager.coerce_float(options.get("stepSize"), 0.01)
        if self.stop_time <= self.current_time:
            raise HTTPException(status_code=400, detail="stopTime must be greater than startTime")
        if self.step_size <= 0:
            raise HTTPException(status_code=400, detail="stepSize must be positive")

        self._shutdown_fmu()
        self._unzipdir = extract(str(self.fmu_path))
        self._fmu = instantiate_fmu(self._unzipdir, self._model_description, fmi_type="CoSimulation")
        self._fmu.instantiate()
        fmi_major = str(getattr(self._model_description, "fmiVersion", "")).split(".", 1)[0]
        if fmi_major == "3":
            self._fmu.enterInitializationMode(startTime=self.current_time, stopTime=self.stop_time)
        else:
            self._fmu.setupExperiment(startTime=self.current_time, stopTime=self.stop_time)
            self._fmu.enterInitializationMode()
        start_inputs = options.get("inputs")
        if isinstance(start_inputs, dict) and start_inputs:
            self._set_values(start_inputs)
        self._fmu.exitInitializationMode()
        self.state = "initialized"
        await self._emit_state()

    async def _step_once(self, delta_t: float, emit_outputs: bool = True):
        self.ensure_reservation_window()
        if self._fmu is None:
            raise HTTPException(status_code=409, detail="Simulation is not initialized")
        if delta_t <= 0:
            raise HTTPException(status_code=400, detail="deltaT must be positive")
        self._fmu.doStep(self.current_time, delta_t)
        self.current_time = self.current_time + delta_t
        await self._enqueue_event({
            "type": "sim.progress",
            "sessionId": self.session_id,
            "simTime": self.current_time,
        })
        if emit_outputs:
            await self._emit_outputs_if_needed()

    async def start(self):
        self.ensure_reservation_window()
        if self._fmu is None:
            raise HTTPException(status_code=409, detail="Simulation is not initialized")
        if self.state == "running":
            return
        self.state = "running"
        await self._emit_state()
        self._runner_task = asyncio.create_task(self._run_loop())

    async def pause(self):
        if self.state != "running":
            return
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
        self._runner_task = None
        self.state = "paused"
        await self._emit_state()

    async def resume(self):
        if self.state == "running":
            return
        if self.state not in ("paused", "initialized"):
            raise HTTPException(status_code=409, detail=f"Cannot resume from state {self.state}")
        await self.start()

    async def reset(self):
        if self._model_description is None:
            self._ensure_model_loaded()
        options = {
            "startTime": 0.0,
            "stopTime": self.stop_time if self.stop_time > 0 else 10.0,
            "stepSize": self.step_size if self.step_size > 0 else 0.01,
        }
        await self.initialize(options)
        self.state = "initialized"
        await self._emit_state()

    async def run_until(self, target_time: float):
        if target_time <= self.current_time:
            return
        while self.current_time < target_time:
            step = min(self.step_size, target_time - self.current_time)
            await self._step_once(step, emit_outputs=False)

    async def terminate(self, reason: str = "terminated"):
        if self._closed:
            return
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
        self._runner_task = None
        await self.detach()
        self._shutdown_fmu()
        self.state = "stopped"
        self._closed = True
        self.manager.release_slot(self.lab_id)
        await self._enqueue_event({
            "type": "session.closed",
            "sessionId": self.session_id,
            "reason": reason,
        })

    async def _run_loop(self):
        try:
            while self.state == "running":
                if self.current_time >= self.stop_time:
                    self.state = "stopped"
                    await self._emit_state()
                    break
                await self._step_once(self.step_size, emit_outputs=True)
                await asyncio.sleep(min(max(self.step_size, 0.01), 1.0))
        except asyncio.CancelledError:
            return
        except HTTPException:
            self.state = "error"
            await self._emit_state()
        except Exception as exc:
            self.manager.logger.error("Realtime runner loop failed for session %s: %s", self.session_id, exc)
            self.state = "error"
            await self._emit_state()


class RealtimeWsManager:
    def __init__(
        self,
        *,
        logger,
        verify_jwt_token,
        enforce_fmu_claim,
        resolve_fmu_path,
        get_claim_lab_id,
        normalize_lab_id,
        coerce_epoch_seconds,
        acquire_slot,
        release_slot,
        redeem_session_ticket=None,
        ws_session_queue_size: int = 64,
        ws_heartbeat_seconds: float = 15.0,
        ws_expiring_notice_seconds: int = 60,
        ws_attach_grace_seconds: int = 120,
        ws_cleanup_seconds: float = 15.0,
        internal_ws_token: str = "",
        ws_create_rate_limit_per_minute: int = 30,
    ):
        self.logger = logger
        self.verify_jwt_token = verify_jwt_token
        self.enforce_fmu_claim = enforce_fmu_claim
        self.resolve_fmu_path = resolve_fmu_path
        self.get_claim_lab_id = get_claim_lab_id
        self.normalize_lab_id = normalize_lab_id
        self.coerce_epoch_seconds = coerce_epoch_seconds
        self.acquire_slot = acquire_slot
        self.release_slot = release_slot
        self.redeem_session_ticket = redeem_session_ticket
        self.ws_session_queue_size = ws_session_queue_size
        self.ws_heartbeat_seconds = ws_heartbeat_seconds
        self.ws_expiring_notice_seconds = ws_expiring_notice_seconds
        self.ws_attach_grace_seconds = ws_attach_grace_seconds
        self.ws_cleanup_seconds = ws_cleanup_seconds
        self.internal_ws_token = internal_ws_token
        self.ws_create_rate_limit_per_minute = ws_create_rate_limit_per_minute

        self._sessions: dict[str, _RealtimeSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._create_hits: dict[str, deque[float]] = defaultdict(deque)

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

    def extract_ws_token(self, websocket: WebSocket) -> str:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        token_param = websocket.query_params.get("token")
        if token_param:
            return token_param
        cookie_header = websocket.headers.get("cookie", "")
        cookies = self.parse_cookie_header(cookie_header)
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

    @staticmethod
    def coerce_float(value: Any, fallback: Optional[float]) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def model_description_payload(md) -> dict:
        simulation_kind = "coSimulation" if md.coSimulation else ("modelExchange" if md.modelExchange else "unknown")
        variables = []
        for var in md.modelVariables:
            entry = {
                "name": var.name,
                "type": str(var.type),
                "causality": var.causality or "local",
                "variability": getattr(var, "variability", None) or "continuous",
            }
            if hasattr(var, "start") and var.start is not None:
                entry["start"] = var.start
            if hasattr(var, "unit") and var.unit:
                entry["unit"] = var.unit
            if getattr(var, "dimensions", None):
                entry["dimensions"] = [
                    {
                        **({"start": int(dim.start)} if getattr(dim, "start", None) is not None else {}),
                        **({"valueReference": int(dim.valueReference)} if getattr(dim, "valueReference", None) is not None else {}),
                        **({"variableName": dim.variable.name} if getattr(dim, "variable", None) is not None and getattr(dim.variable, "name", None) else {}),
                    }
                    for dim in var.dimensions
                ]
            variables.append(entry)
        return {
            "fmiVersion": md.fmiVersion,
            "simulationKind": simulation_kind,
            "variables": variables,
        }

    async def start(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await session.terminate(reason="service_shutdown")

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.ws_cleanup_seconds)
            now = time.time()
            async with self._sessions_lock:
                sessions = list(self._sessions.values())
            for session in sessions:
                if session.is_closed():
                    async with self._sessions_lock:
                        self._sessions.pop(session.session_id, None)
                    continue
                if session.exp is not None and now >= session.exp:
                    await session.terminate(reason="expired")
                    async with self._sessions_lock:
                        self._sessions.pop(session.session_id, None)
                    continue
                if session.connection is None and session.attach_deadline is not None and now >= session.attach_deadline:
                    await session.terminate(reason="detached_timeout")
                    async with self._sessions_lock:
                        self._sessions.pop(session.session_id, None)

    async def _send_direct(self, connection: _WsConnection, payload: dict):
        async with connection.send_lock:
            await connection.websocket.send_json(payload)

    async def handle_websocket(self, websocket: WebSocket, *, internal: bool):
        await websocket.accept()
        connection = _WsConnection(websocket=websocket, queue_size=self.ws_session_queue_size)
        current_session: Optional[_RealtimeSession] = None
        local_request_cache: dict[str, dict] = {}

        try:
            if internal and self.internal_ws_token:
                provided = websocket.headers.get("x-internal-session-token", "")
                if not secrets.compare_digest(provided, self.internal_ws_token):
                    await self._send_direct(connection, self.error_payload(code="FORBIDDEN", message="Invalid internal token"))
                    await websocket.close(code=1008)
                    return

            claims: Optional[dict] = None
            try:
                token = self.extract_ws_token(websocket)
                claims = await self.verify_jwt_token(token)
                self.enforce_fmu_claim(claims)
            except HTTPException as exc:
                # Ticket-only sessions are allowed to connect without a bearer token.
                if exc.status_code != 401:
                    raise

            while True:
                raw_message = await websocket.receive_text()
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._send_direct(connection, self.error_payload(code="INVALID_COMMAND", message="Invalid JSON payload"))
                    continue

                msg_type = str(message.get("type") or "").strip()
                request_id = str(message.get("requestId") or "").strip()
                if not msg_type:
                    await self._send_direct(connection, self.error_payload(code="INVALID_COMMAND", message="Missing message type"))
                    continue
                if not request_id:
                    await self._send_direct(connection, self.error_payload(code="INVALID_COMMAND", message="Missing requestId"))
                    continue

                if request_id in local_request_cache:
                    await self._send_direct(connection, local_request_cache[request_id])
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
                        await self._send_direct(connection, response)
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
                            await self._send_direct(connection, response)
                            local_request_cache[request_id] = response
                            continue
                        if self.redeem_session_ticket is None:
                            response = self.error_payload(
                                code="INTERNAL_ERROR",
                                message="Session ticket redemption is not configured",
                                request_id=request_id,
                                retryable=False,
                            )
                            await self._send_direct(connection, response)
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
                                "session.create ticket redeem failed request_id=%s lab_id=%s reservation_key=%s ticket_id=%s code=%s",
                                request_id,
                                req_lab_id or "-",
                                reservation_key or "-",
                                self._normalize_ticket_id(session_ticket) or "-",
                                code,
                            )
                            await self._send_direct(connection, response)
                            local_request_cache[request_id] = response
                            continue

                    claim_lab_id = self.get_claim_lab_id(create_claims)
                    if claim_lab_id and req_lab_id and claim_lab_id != req_lab_id:
                        response = self.error_payload(
                            code="LAB_MISMATCH",
                            message="JWT not authorised for requested labId",
                            request_id=request_id,
                            retryable=False,
                        )
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue

                    access_key = create_claims.get("accessKey") or create_claims.get("fmuFileName")
                    if not access_key:
                        response = self.error_payload(
                            code="FORBIDDEN",
                            message="Token has no authorised FMU file",
                            request_id=request_id,
                            retryable=False,
                        )
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue
                    try:
                        fmu_path = self.resolve_fmu_path(str(access_key))
                        self.acquire_slot(claim_lab_id or req_lab_id or "unknown")
                        session_id = "sess_" + uuid4().hex[:12]
                        session = _RealtimeSession(self, session_id, create_claims, fmu_path)
                        session.ensure_reservation_window()
                        await session.attach(connection)
                        async with self._sessions_lock:
                            self._sessions[session_id] = session
                        current_session = session
                        response = {
                            "type": "session.created",
                            "requestId": request_id,
                            "sessionId": session_id,
                            "serverTime": int(time.time()),
                            "expiresAt": session.exp,
                            "reservationWindow": {"nbf": session.nbf, "exp": session.exp},
                            "capabilities": session.capabilities,
                        }
                        self.logger.info(
                            "session.create success request_id=%s session_id=%s lab_id=%s reservation_key=%s ticket_id=%s",
                            request_id,
                            session_id,
                            claim_lab_id or req_lab_id or "-",
                            reservation_key or "-",
                            self._normalize_ticket_id(session_ticket) or "-",
                        )
                    except HTTPException as exc:
                        response = self.error_payload(
                            code="RESERVATION_NOT_ACTIVE" if exc.status_code == 403 else ("SESSION_EXPIRED" if exc.status_code == 401 else "INTERNAL_ERROR"),
                            message=str(exc.detail),
                            request_id=request_id,
                            retryable=exc.status_code >= 500,
                        )
                    local_request_cache[request_id] = response
                    await self._send_direct(connection, response)
                    continue

                if msg_type == "session.attach":
                    if claims is None:
                        response = self.error_payload(
                            code="UNAUTHORIZED",
                            message="session.attach requires a bearer token",
                            request_id=request_id,
                            retryable=False,
                        )
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue
                    session_id = str(message.get("sessionId") or "").strip()
                    if not session_id:
                        response = self.error_payload(code="INVALID_COMMAND", message="Missing sessionId", request_id=request_id)
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue
                    async with self._sessions_lock:
                        session = self._sessions.get(session_id)
                    if not session:
                        response = self.error_payload(code="FORBIDDEN", message="Session not found", request_id=request_id, retryable=False)
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue
                    if not session.matches_claims(claims):
                        response = self.error_payload(code="FORBIDDEN", message="Session ownership mismatch", request_id=request_id)
                        await self._send_direct(connection, response)
                        local_request_cache[request_id] = response
                        continue
                    await session.attach(connection)
                    current_session = session
                    response = {
                        "type": "session.attached",
                        "requestId": request_id,
                        "sessionId": session.session_id,
                        "serverTime": int(time.time()),
                        "expiresAt": session.exp,
                        "state": session.state,
                    }
                    local_request_cache[request_id] = response
                    await self._send_direct(connection, response)
                    continue

                if current_session is None:
                    response = self.error_payload(code="FORBIDDEN", message="Create or attach a session first", request_id=request_id)
                    await self._send_direct(connection, response)
                    local_request_cache[request_id] = response
                    continue

                cached = current_session.get_cached(request_id)
                if cached is not None:
                    await self._send_direct(connection, cached)
                    continue

                try:
                    current_session.ensure_reservation_window()
                    if msg_type == "session.ping":
                        response = {
                            "type": "session.pong",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "serverTime": int(time.time()),
                        }
                    elif msg_type == "model.describe":
                        current_session._ensure_model_loaded()
                        payload = current_session._model_payload or {}
                        response = {
                            "type": "model.description",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            **payload,
                        }
                    elif msg_type == "sim.initialize":
                        await current_session.initialize(message.get("options") or {})
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.start":
                        await current_session.start()
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.pause":
                        await current_session.pause()
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.resume":
                        await current_session.resume()
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.reset":
                        await current_session.reset()
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.step":
                        delta_t = self.coerce_float(message.get("deltaT"), current_session.step_size) or current_session.step_size
                        await current_session._step_once(delta_t, emit_outputs=False)
                        outputs = current_session._sample_outputs()
                        response = {
                            "type": "sim.outputs",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "seq": current_session.seq,
                            "dropped": current_session._pending_queue_drops,
                            "simTime": current_session.current_time,
                            "values": outputs,
                        }
                    elif msg_type == "sim.runUntil":
                        target_time = self.coerce_float(message.get("time"), current_session.current_time) or current_session.current_time
                        await current_session.run_until(target_time)
                        outputs = current_session._sample_outputs()
                        response = {
                            "type": "sim.outputs",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "seq": current_session.seq,
                            "dropped": current_session._pending_queue_drops,
                            "simTime": current_session.current_time,
                            "values": outputs,
                        }
                    elif msg_type == "sim.setInputs":
                        values = message.get("values")
                        if not isinstance(values, dict):
                            raise HTTPException(status_code=400, detail="sim.setInputs requires an object 'values'")
                        current_session._set_values(values)
                        response = {
                            "type": "sim.inputs.updated",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.getOutputs":
                        variables = message.get("variables")
                        if variables is None:
                            variables = current_session._default_output_variables()
                        if not isinstance(variables, list):
                            raise HTTPException(status_code=400, detail="sim.getOutputs requires 'variables' as array")
                        outputs = current_session._get_values(variables)
                        response = {
                            "type": "sim.outputs",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "seq": current_session.seq,
                            "dropped": current_session._pending_queue_drops,
                            "simTime": current_session.current_time,
                            "values": outputs,
                        }
                    elif msg_type == "sim.getState":
                        response = {
                            "type": "sim.state",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "state": current_session.state,
                            "simTime": current_session.current_time,
                        }
                    elif msg_type == "sim.subscribeOutputs":
                        variables = message.get("variables")
                        if variables is not None and not isinstance(variables, list):
                            raise HTTPException(status_code=400, detail="sim.subscribeOutputs requires 'variables' as array")
                        subscription = _StreamSubscription(
                            variables=variables,
                            period_ms=max(1, int(message.get("periodMs", 100))),
                            max_batch_size=max(1, int(message.get("maxBatchSize", 64))),
                            max_hz=self.coerce_float(message.get("maxHz"), None) if message.get("maxHz") is not None else None,
                        )
                        current_session.subscription = subscription
                        response = {
                            "type": "sim.subscribed",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "periodMs": subscription.period_ms,
                            "maxBatchSize": subscription.max_batch_size,
                            "maxHz": subscription.max_hz,
                        }
                    elif msg_type == "sim.unsubscribeOutputs":
                        current_session.subscription = None
                        current_session._pending_samples.clear()
                        response = {
                            "type": "sim.unsubscribed",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                        }
                    elif msg_type == "session.terminate":
                        already_closed = current_session.is_closed()
                        await current_session.terminate(reason="client_terminated")
                        async with self._sessions_lock:
                            self._sessions.pop(current_session.session_id, None)
                        response = {
                            "type": "session.closed",
                            "requestId": request_id,
                            "sessionId": current_session.session_id,
                            "reason": "already_closed" if already_closed else "client_terminated",
                        }
                    else:
                        response = self.error_payload(
                            code="INVALID_COMMAND",
                            message=f"Unsupported command: {msg_type}",
                            request_id=request_id,
                            retryable=False,
                            session_id=current_session.session_id,
                        )
                except HTTPException as exc:
                    code = "INTERNAL_ERROR"
                    if exc.status_code == 401:
                        code = "SESSION_EXPIRED"
                    elif exc.status_code == 403:
                        code = "RESERVATION_NOT_ACTIVE"
                    elif exc.status_code in (400, 404, 409):
                        code = "INVALID_COMMAND"
                    response = self.error_payload(
                        code=code,
                        message=str(exc.detail),
                        request_id=request_id,
                        retryable=exc.status_code >= 500,
                        session_id=current_session.session_id,
                    )
                except Exception as exc:
                    self.logger.error("Realtime WS command failed: %s", exc)
                    response = self.error_payload(
                        code="INTERNAL_ERROR",
                        message=str(exc),
                        request_id=request_id,
                        retryable=False,
                        session_id=current_session.session_id,
                    )

                current_session.cache_response(request_id, response)
                await self._send_direct(connection, response)

        except WebSocketDisconnect:
            pass
        except HTTPException as exc:
            await self._send_direct(
                connection,
                self.error_payload(
                    code="UNAUTHORIZED" if exc.status_code == 401 else "FORBIDDEN",
                    message=str(exc.detail),
                    retryable=False,
                ),
            )
        finally:
            if current_session is not None and current_session.connection is connection:
                await current_session.detach()
            try:
                await websocket.close()
            except Exception:
                pass
