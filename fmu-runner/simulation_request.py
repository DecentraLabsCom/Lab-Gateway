"""Validated request model shared by FMU simulation routes."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


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


__all__ = ["SimulationRequest"]
