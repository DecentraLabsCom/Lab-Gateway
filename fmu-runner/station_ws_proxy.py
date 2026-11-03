from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
from collections import defaultdict, deque
from typing import Any, Optional

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
MAX_FMU_STATE_CHECKPOINT_BYTES = 4096









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
    def _validate_session_message(
        message: dict,
        access_policy: dict,
        model_metadata: Optional[dict] = None,
        active_session=None,
    ) -> None:
        """Authorize FMI variable reads/writes before forwarding a command."""
        msg_type = str(message.get("type") or "").strip()
        if msg_type == "sim.initialize":
            parameters = message.get("parameters", {})
            options = message.get("options", {})
            if not isinstance(parameters, dict) or not isinstance(options, dict):
                raise AccessDenied
            requested_interface = options.get("executionInterface")
            external_solver = options.get("externalSolver", False)
            if type(external_solver) is not bool:
                raise AccessDenied
            defer_initialization_exit = options.get("deferInitializationExit", False)
            if type(defer_initialization_exit) is not bool:
                raise AccessDenied
            if requested_interface is not None:
                if requested_interface not in {"CoSimulation", "ModelExchange"}:
                    raise AccessDenied
                authorized_interfaces = access_policy.get("authorizedExecutionInterfaces")
                if not isinstance(authorized_interfaces, list) or requested_interface not in authorized_interfaces:
                    raise AccessDenied
            if external_solver and requested_interface != "ModelExchange":
                raise AccessDenied
            if defer_initialization_exit and not external_solver:
                raise AccessDenied
            checkpoint = message.get("checkpoint")
            if checkpoint is not None:
                StationRealtimeWsProxyManager._validate_state_checkpoint(checkpoint)
            model_variables = access_policy.get("modelVariables", [])
            metadata_variables = model_metadata.get("modelVariables", []) if isinstance(model_metadata, dict) else []
            model_structure = model_metadata.get("modelStructure", {}) if isinstance(model_metadata, dict) else {}
            derivative_entries = model_structure.get("derivatives", []) if isinstance(model_structure, dict) else []
            state_references = {
                entry.get("stateValueReference")
                for entry in derivative_entries
                if isinstance(entry, dict)
                and type(entry.get("stateValueReference")) is int
            }
            fmi_version = model_metadata.get("fmiVersion") if isinstance(model_metadata, dict) else None
            state_initial_names = {
                variable.get("name")
                for variable in metadata_variables
                if isinstance(variable, dict)
                and variable.get("valueReference") in state_references
                and isinstance(variable.get("name"), str)
                and (
                    variable.get("initial") == "exact"
                    or (str(fmi_version).startswith("2.") and variable.get("initial") == "approx")
                )
            } if isinstance(metadata_variables, list) else set()
            structural_parameter_names = {
                variable.get("name")
                for variable in model_variables
                if isinstance(variable, dict)
                and variable.get("causality") == "structuralParameter"
                and isinstance(variable.get("name"), str)
            } if isinstance(model_variables, list) else set()
            configuration_values = {
                name: value for name, value in parameters.items()
                if name in structural_parameter_names
            }
            initialization_values = {
                name: value for name, value in parameters.items()
                if name not in structural_parameter_names and name not in state_initial_names
            }
            validate_writes(access_policy, initialization_values, phase="initialization")
            validate_writes(access_policy, configuration_values, phase="configuration")
            state_initial_values = {
                name: value for name, value in parameters.items() if name in state_initial_names
            }
            if state_initial_values:
                if not external_solver or requested_interface != "ModelExchange":
                    raise AccessDenied
                state_policy = dict(access_policy)
                state_permissions = dict(access_policy.get("variables", {}))
                for name in state_initial_values:
                    permission = dict(state_permissions.get(name, {}))
                    write_phases = permission.get("writeAt", [])
                    permission["writeAt"] = list(dict.fromkeys([*write_phases, "initialization"]))
                    state_permissions[name] = permission
                state_policy["variables"] = state_permissions
                validate_writes(state_policy, state_initial_values, phase="initialization")
            if "inputs" in options:
                validate_writes(access_policy, options["inputs"], phase="initialization")
            if active_session is not None:
                active_session.model_exchange_mode = (
                    "initialization" if external_solver and defer_initialization_exit
                    else "event" if external_solver
                    else "instantiated"
                )
        elif msg_type == "sim.restoreFMUState":
            StationRealtimeWsProxyManager._validate_state_checkpoint(message.get("checkpoint"))
            variables = message.get("variables", [])
            if (
                not isinstance(variables, list)
                or len(variables) > 512
                or any(not isinstance(name, str) or not name or len(name) > 256 for name in variables)
                or len(set(variables)) != len(variables)
            ):
                raise AccessDenied
            validate_reads(access_policy, variables)
        elif msg_type == "sim.setInputs":
            validate_writes(access_policy, message.get("values", {}), phase="runtime")
        elif msg_type == "sim.reconfigure":
            values = message.get("values", {})
            if not isinstance(values, dict) or not values:
                raise AccessDenied
            validate_writes(access_policy, values, phase="reconfiguration")
        elif msg_type == "sim.advance":
            input_values = message.get("inputValues", {})
            if not isinstance(input_values, dict):
                raise AccessDenied
            if input_values:
                validate_writes(access_policy, input_values, phase="runtime")
            max_compute_ms = message.get("maxComputeMs")
            if max_compute_ms is not None and (
                isinstance(max_compute_ms, bool)
                or not isinstance(max_compute_ms, (int, float))
                or not math.isfinite(max_compute_ms)
                or not 1 <= max_compute_ms <= MAX_ADVANCE_COMPUTE_MS
            ):
                raise AccessDenied
            input_schedule = message.get("inputSchedule", [])
            if (
                not isinstance(input_schedule, list)
                or len(input_schedule) + bool(input_values) > MAX_ADVANCE_INPUT_EVENTS
            ):
                raise AccessDenied
            try:
                schedule_bytes = len(json.dumps(
                    input_schedule,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"))
                input_values_bytes = len(json.dumps(
                    input_values,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"))
            except (TypeError, ValueError):
                raise AccessDenied
            if schedule_bytes + input_values_bytes > MAX_ADVANCE_INPUT_BYTES:
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
        elif msg_type == "sim.modelExchangeCall":
            if "ModelExchange" not in access_policy.get("authorizedExecutionInterfaces", []):
                raise AccessDenied
            operation = message.get("operation")
            arguments = message.get("arguments", {})
            if not isinstance(arguments, dict):
                raise AccessDenied
            allowed_arguments = {
                "setTime": {"time"},
                "exitInitializationMode": set(),
                "getContinuousStates": set(),
                "setContinuousStates": {"values"},
                "getDerivatives": set(),
                "getContinuousStateDerivatives": set(),
                "getEventIndicators": set(),
                "getNominalsOfContinuousStates": set(),
                "completedIntegratorStep": {"noSetFMUStatePriorToCurrentPoint"},
                "enterEventMode": set(),
                "newDiscreteStates": set(),
                "updateDiscreteStates": set(),
                "enterContinuousTimeMode": set(),
                "getNumberOfContinuousStates": set(),
                "getNumberOfEventIndicators": set(),
                "getValues": {"valueType", "valueReferences"},
                "setValues": {"valueType", "valueReferences", "values"},
            }
            if operation not in allowed_arguments or set(arguments) != allowed_arguments[operation]:
                raise AccessDenied
            if active_session is None:
                raise AccessDenied
            fmi_major = (
                str(model_metadata.get("fmiVersion", "")).split(".", 1)[0]
                if isinstance(model_metadata, dict)
                else ""
            )
            mode = getattr(active_session, "model_exchange_mode", "continuous")
            allowed_modes = {
                "setTime": {"continuous"} if fmi_major == "3" else {"event", "continuous"},
                "exitInitializationMode": {"initialization"},
                "getContinuousStates": {"initialization", "event", "continuous"},
                "setContinuousStates": {"event", "continuous"} if fmi_major == "2" else {"continuous"},
                "getDerivatives": {"initialization", "event", "continuous"},
                "getContinuousStateDerivatives": {"initialization", "event", "continuous"},
                "getEventIndicators": {"initialization", "event", "continuous"},
                "getNominalsOfContinuousStates": (
                    {"initialization", "event", "continuous"}
                    if fmi_major == "3"
                    else {"event", "continuous"}
                ),
                "completedIntegratorStep": {"continuous"},
                "enterEventMode": {"continuous"},
                "newDiscreteStates": {"event"},
                "updateDiscreteStates": {"event"},
                "enterContinuousTimeMode": {"event"},
                "getNumberOfContinuousStates": {"instantiated", "initialization", "event", "continuous"},
                "getNumberOfEventIndicators": {"instantiated", "initialization", "event", "continuous"},
                "getValues": {"initialization", "event", "continuous"},
                "setValues": {"initialization", "event", "continuous"},
            }
            if fmi_major not in {"2", "3"} or mode not in allowed_modes[operation]:
                raise AccessDenied
            if operation == "setTime":
                value = arguments.get("time")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise AccessDenied
            elif operation in {"setContinuousStates", "getContinuousStates", "getDerivatives", "getContinuousStateDerivatives", "getEventIndicators", "getNominalsOfContinuousStates"}:
                values = arguments.get("values")
                if operation == "setContinuousStates" and (
                    not isinstance(values, list)
                    or len(values) > 100_000
                    or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values)
                ):
                    raise AccessDenied
            elif operation == "completedIntegratorStep":
                value = arguments.get("noSetFMUStatePriorToCurrentPoint", True)
                if type(value) is not bool:
                    raise AccessDenied
            elif operation in {"getValues", "setValues"}:
                value_type = arguments.get("valueType")
                raw_references = arguments.get("valueReferences")
                if (
                    not isinstance(value_type, str)
                    or value_type not in {"Real", "Float32", "Float64", "Integer", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Boolean", "String", "Binary", "Clock", "Enumeration"}
                    or not isinstance(raw_references, list)
                    or not raw_references
                    or len(raw_references) > 512
                ):
                    raise AccessDenied
                references: list[int] = []
                for raw_reference in raw_references:
                    if type(raw_reference) is not int or raw_reference < 0 or raw_reference > 0xFFFFFFFF:
                        raise AccessDenied
                    references.append(raw_reference)
                if model_metadata is None or not isinstance(model_metadata.get("modelVariables"), list):
                    raise AccessDenied
                variables_by_reference: dict[int, list[dict]] = {}
                for variable in model_metadata["modelVariables"]:
                    if not isinstance(variable, dict):
                        continue
                    reference = variable.get("valueReference")
                    if type(reference) is not int or not isinstance(variable.get("name"), str):
                        continue
                    variables_by_reference.setdefault(reference, []).append(variable)
                if any(reference not in variables_by_reference for reference in references):
                    raise AccessDenied
                dae_metadata = model_metadata.get("fmiLsDae") if isinstance(model_metadata, dict) else None
                dae_algebraic_references = set(dae_metadata.get("algebraicValueReferences", [])) if isinstance(dae_metadata, dict) else set()
                dae_residual_references = set(dae_metadata.get("residualValueReferences", [])) if isinstance(dae_metadata, dict) else set()
                model_structure = model_metadata.get("modelStructure", {}) if isinstance(model_metadata, dict) else {}
                derivative_entries = model_structure.get("derivatives", []) if isinstance(model_structure, dict) else []
                state_references = {
                    entry.get("stateValueReference")
                    for entry in derivative_entries
                    if isinstance(entry, dict) and type(entry.get("stateValueReference")) is int
                }
                permissions = access_policy.get("variables", {})
                mode = getattr(active_session, "model_exchange_mode", "continuous")
                fmi_major = str(model_metadata.get("fmiVersion", "")).split(".", 1)[0]
                if operation == "getValues":
                    for reference in references:
                        if reference in dae_residual_references or reference in dae_algebraic_references or reference in state_references:
                            continue
                        names = [item.get("name") for item in variables_by_reference[reference]]
                        if not any(
                            isinstance(name, str)
                            and isinstance(permissions.get(name), dict)
                            and permissions[name].get("read") is True
                            for name in names
                        ):
                            raise AccessDenied
                else:
                    values = arguments.get("values")
                    if not isinstance(values, list) or len(values) > 100_000:
                        raise AccessDenied
                    phase = "initialization" if mode == "initialization" else "runtime"
                    for reference in references:
                        variables = variables_by_reference[reference]
                        if reference in dae_algebraic_references:
                            if mode not in {"event", "continuous"}:
                                raise AccessDenied
                            continue
                        if reference in state_references:
                            state_writable = any(
                                (mode == "initialization" and variable.get("initial") == "exact")
                                or (fmi_major == "3" and mode == "continuous")
                                or (
                                    fmi_major == "3"
                                    and mode == "event"
                                    and variable.get("reinit") is False
                                )
                                for variable in variables
                            )
                            if not state_writable:
                                raise AccessDenied
                            continue

                        def standard_writable(variable: dict) -> bool:
                            causality = variable.get("causality")
                            variability = variable.get("variability")
                            if mode == "initialization":
                                return causality == "input" or (
                                    causality == "parameter"
                                    and (
                                        fmi_major == "2" and variability != "constant"
                                        or fmi_major == "3" and variable.get("initial") == "exact"
                                    )
                                )
                            if mode == "event":
                                return causality == "input" or (
                                    causality == "parameter" and variability == "tunable"
                                )
                            if mode == "continuous":
                                return causality == "input" and variability == "continuous"
                            return False

                        authorized = any(
                            standard_writable(variable)
                            and isinstance(variable.get("name"), str)
                            and isinstance(permissions.get(variable["name"]), dict)
                            and isinstance(permissions[variable["name"]].get("writeAt"), list)
                            and phase in permissions[variable["name"]]["writeAt"]
                            for variable in variables
                        )
                        if not authorized:
                            raise AccessDenied
            if active_session is not None:
                if operation in {"exitInitializationMode", "enterEventMode"}:
                    active_session.model_exchange_mode = "event"
                elif operation == "enterContinuousTimeMode":
                    active_session.model_exchange_mode = "continuous"
            else:
                raise AccessDenied

    @staticmethod
    def _validate_state_checkpoint(checkpoint: Any) -> None:
        if not isinstance(checkpoint, dict):
            raise AccessDenied
        try:
            encoded = json.dumps(checkpoint, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            raise AccessDenied
        if len(encoded) > MAX_FMU_STATE_CHECKPOINT_BYTES:
            raise AccessDenied

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
        # Large FMUs can return model descriptions larger than
        # websockets' 1 MiB default. Keep this bounded and leave the
        # browser-facing request/sample limits unchanged.
        connect_kwargs["max_size"] = 32 * 1024 * 1024
        connect_kwargs["max_queue"] = 1
        return await websockets.connect(self.station_backend.station_session_ws_url(), **connect_kwargs)

    async def handle_websocket(self, websocket: WebSocket, *, internal: bool):
        await StationWebSocketConnection(self).run(websocket, internal=internal)
