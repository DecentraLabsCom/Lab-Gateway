"""Bounded public request models for reservation-scoped FMU simulations."""

import json
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _validate_parameters(value: dict) -> dict:
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError("A simulation may set at most 32 parameters")
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


class SimulationRequest(BaseModel):
    reservationKey: Optional[str] = None
    labId: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)

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
