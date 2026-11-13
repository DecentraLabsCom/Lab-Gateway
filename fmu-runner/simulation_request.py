"""Bounded public request models for reservation-scoped FMU simulations."""

import json
import math
from typing import Any, Optional

from pydantic import BaseModel, Field, StrictBool, field_validator

from config import CONFIG

_MAX_SIMULATION_PARAMETERS = CONFIG.max_simulation_parameters


def _validate_parameters(value: dict) -> dict:
    if not isinstance(value, dict) or len(value) > _MAX_SIMULATION_PARAMETERS:
        raise ValueError(f"A simulation may set at most {_MAX_SIMULATION_PARAMETERS} parameters")
    if any(not isinstance(key, str) or not key or len(key) > 128 for key in value):
        raise ValueError("Simulation parameter names are invalid")

    def validate_value(item, depth=0):
        if isinstance(item, list):
            if depth >= 4 or len(item) > 4096:
                raise ValueError("Simulation parameter array is too large")
            return sum(validate_value(entry, depth + 1) for entry in item)
        if item is None or isinstance(item, dict) or not isinstance(item, (str, int, float, bool)):
            raise ValueError("Simulation parameter values must be scalar or arrays")
        if isinstance(item, str) and len(item) > 4096:
            raise ValueError("Simulation parameter value is too large")
        return 1

    if any(validate_value(item) > 4096 for item in value.values()):
        raise ValueError("Simulation parameter array is too large")
    try:
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Simulation parameters must contain finite JSON values") from exc
    if len(encoded.encode("utf-8")) > 16 * 1024:
        raise ValueError("Simulation parameter payload exceeds 16 KiB")
    return value


def _validate_input_schedule(value: list) -> list:
    if not isinstance(value, list) or len(value) > CONFIG.max_input_schedule_events:
        raise ValueError(
            "A simulation can contain at most "
            f"{CONFIG.max_input_schedule_events} scheduled variable changes"
        )
    normalized_events = []
    seen_values: set[tuple[float, str]] = set()
    for event in value:
        if not isinstance(event, dict) or set(event) != {"time", "values"}:
            raise ValueError("Each scheduled variable change must contain only time and values")
        time_value = event["time"]
        if isinstance(time_value, bool) or not isinstance(time_value, (int, float)) or not math.isfinite(float(time_value)):
            raise ValueError("Scheduled variable times must be finite numbers")
        values = _validate_parameters(event["values"])
        if not values:
            raise ValueError("Each scheduled variable change must contain at least one value")
        for name in values:
            identity = (float(time_value), name)
            if identity in seen_values:
                raise ValueError("A variable may only have one scheduled value at the same simulation time")
            seen_values.add(identity)
        normalized_events.append({"time": float(time_value), "values": values})
    try:
        encoded = json.dumps(normalized_events, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Scheduled changes must contain finite JSON values") from exc
    if len(encoded.encode("utf-8")) > CONFIG.max_input_schedule_bytes:
        raise ValueError("Scheduled changes exceed the configured size limit")
    return normalized_events


class SimulationRequest(BaseModel):
    reservationKey: Optional[str] = None
    labId: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)
    checkpoint: Optional[dict[str, Any]] = None
    captureFmuState: StrictBool = False
    inputSchedule: list[dict] = Field(
        default_factory=list,
        max_length=CONFIG.max_input_schedule_events,
    )

    @field_validator("labId", mode="before")
    @classmethod
    def _normalize_lab_id(cls, value):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        return value

    @field_validator("parameters")
    @classmethod
    def _bounded_parameters(cls, value):
        return _validate_parameters(value)

    @field_validator("inputSchedule")
    @classmethod
    def _bounded_input_schedule(cls, value):
        return _validate_input_schedule(value)

    @field_validator("checkpoint")
    @classmethod
    def _bounded_checkpoint(cls, value):
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("FMU state checkpoint must be an object")
        try:
            encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("FMU state checkpoint is invalid") from exc
        if len(encoded) > 4096:
            raise ValueError("FMU state checkpoint exceeds 4 KiB")
        return value


class BatchScenarioRequest(BaseModel):
    label: Optional[str] = Field(default=None, max_length=80)
    parameters: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def _bounded_parameters(cls, value):
        return _validate_parameters(value)


class BatchSimulationRequest(BaseModel):
    reservationKey: Optional[str] = None
    labId: Optional[str] = None
    options: dict = Field(default_factory=dict)
    scenarios: list[BatchScenarioRequest] = Field(min_length=1, max_length=8)

    @field_validator("labId", mode="before")
    @classmethod
    def _normalize_lab_id(cls, value):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        return value


__all__ = ["BatchScenarioRequest", "BatchSimulationRequest", "SimulationRequest"]
