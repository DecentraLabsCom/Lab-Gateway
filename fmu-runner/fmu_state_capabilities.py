"""Normalize FMI model state support for client-facing access metadata."""

from collections.abc import Mapping
from typing import Any


def normalize_fmu_state_capabilities(model_description: Any) -> dict[str, bool] | None:
    """Return the state capabilities needed by the runtime, when declared."""
    if not isinstance(model_description, Mapping):
        return None
    if model_description.get("simulationType") != "CoSimulation":
        return None

    capabilities = model_description.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None

    aliases = {
        "getAndSet": ("canGetAndSetFMUstate", "canGetAndSetFMUState"),
        "serialize": ("canSerializeFMUstate", "canSerializeFMUState"),
    }
    declared: dict[str, bool] = {}
    for output_name, names in aliases.items():
        for name in names:
            value = capabilities.get(name)
            if isinstance(value, bool):
                declared[output_name] = value
                break

    if not declared:
        return None
    return {
        "getAndSet": declared.get("getAndSet", False),
        "serialize": declared.get("serialize", False),
    }
