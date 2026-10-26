"""FMI-derived variable permissions and restrictive provider overrides."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


POLICY_VERSION = "fmi-variable-access-v1"

_PHASES = ("initialization", "runtime")

_PHASE_SET = frozenset(_PHASES)

_FMI_CAUSALITIES = frozenset({
    "calculatedParameter", "independent", "input", "local", "output",
    "parameter", "structuralParameter",
})

_FMI_VARIABILITIES = frozenset({"constant", "continuous", "discrete", "fixed", "tunable"})

_MAX_VARIABLES = 100_000

_MAX_VARIABLE_NAME_LENGTH = 1024

def _supports_runtime_tunable_parameters(metadata: Mapping[str, Any]) -> bool:
    try:
        fmi_major = int(str(metadata.get("fmiVersion") or "").split(".", 1)[0])
    except (TypeError, ValueError):
        return False
    simulation_type = re.sub(
        r"[^a-z]",
        "",
        str(metadata.get("simulationType") or metadata.get("simulationKind") or "").lower(),
    )
    # The Gateway's current executor path is FMI Co-Simulation. Both FMI 2.0
    # and FMI 3.0 allow tunable parameters to change at communication points.
    return fmi_major in {2, 3} and simulation_type == "cosimulation"


def _default_permissions(
    variable: Mapping[str, Any],
    *,
    supports_runtime_tunable_parameters: bool = False,
) -> dict[str, Any]:
    causality = str(variable.get("causality") or "local").strip()
    variability = str(variable.get("variability") or "continuous").strip()
    if causality not in _FMI_CAUSALITIES:
        return {"read": False, "writeAt": []}
    # FMI causality distinguishes the public model interface from local
    # implementation variables. Treat every non-local variable as readable by
    # default, then let a provider's AAS policy restrict it when needed.
    read = causality != "local"
    write_at: list[str] = []

    if variability not in _FMI_VARIABILITIES:
        return {"read": read, "writeAt": []}

    if causality == "input":
        write_at.append("initialization")
        # The Executor currently permits runtime writes to inputs. FMI constant
        # inputs remain fixed after initialization, so scheduled/runtime writes
        # are not granted for those variables.
        if variability in {"continuous", "discrete", "tunable"}:
            write_at.append("runtime")
    elif causality == "parameter" and variability in {"fixed", "tunable"}:
        write_at.append("initialization")
        if variability == "tunable" and supports_runtime_tunable_parameters:
            # FMI 3 Co-Simulation accepts tunable parameters at communication
            # points; the Executor applies them before the corresponding doStep.
            write_at.append("runtime")

    return {"read": read, "writeAt": write_at}


def _validated_override(
    name: str,
    default: Mapping[str, Any],
    override: Any,
) -> dict[str, Any]:
    if not isinstance(override, Mapping) or set(override) - {"read", "writeAt"}:
        raise ValueError(f"invalid access rule for FMI variable {name!r}")

    read = default["read"]
    if "read" in override:
        requested_read = override["read"]
        if not isinstance(requested_read, bool):
            raise ValueError(f"invalid read permission for FMI variable {name!r}")
        if requested_read and not read:
            raise ValueError(f"access policy cannot grant unsupported access to FMI variable {name!r}")
        read = requested_read

    write_at = list(default["writeAt"])
    if "writeAt" in override:
        requested_write_at = override["writeAt"]
        if (
            not isinstance(requested_write_at, list)
            or any(not isinstance(phase, str) or phase not in _PHASE_SET for phase in requested_write_at)
            or len(requested_write_at) != len(set(requested_write_at))
        ):
            raise ValueError(f"invalid write phases for FMI variable {name!r}")
        if any(phase not in default["writeAt"] for phase in requested_write_at):
            raise ValueError(f"access policy cannot grant unsupported access to FMI variable {name!r}")
        write_at = [phase for phase in _PHASES if phase in requested_write_at]

    return {"read": read, "writeAt": write_at}


def build_effective_policy(
    metadata: Mapping[str, Any],
    *,
    overrides: Mapping[str, Any] | None = None,
    source: str = "fmi-default",
) -> dict[str, Any]:
    """Compile FMI defaults and optional restrictive provider overrides.

    Overrides can only remove rights from the runtime-supported FMI defaults.
    Unknown variables, duplicate names, malformed rules, and attempts to grant
    unsupported rights fail closed.
    """
    if not isinstance(metadata, Mapping):
        raise ValueError("FMU metadata is invalid")
    raw_variables = metadata.get("modelVariables")
    if not isinstance(raw_variables, list) or len(raw_variables) > _MAX_VARIABLES:
        raise ValueError("FMU variable metadata is invalid")

    variables: dict[str, dict[str, Any]] = {}
    supports_runtime_tunable_parameters = _supports_runtime_tunable_parameters(metadata)
    for variable in raw_variables:
        if not isinstance(variable, Mapping):
            raise ValueError("FMU variable metadata is invalid")
        name = variable.get("name")
        if not isinstance(name, str) or not name or len(name) > _MAX_VARIABLE_NAME_LENGTH:
            raise ValueError("FMU variable name is invalid")
        if name in variables:
            raise ValueError(f"duplicate FMI variable name {name!r}")
        variables[name] = _default_permissions(
            variable,
            supports_runtime_tunable_parameters=supports_runtime_tunable_parameters,
        )

    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise ValueError("AAS variable access rules are invalid")
        unknown = set(overrides) - set(variables)
        if unknown:
            raise ValueError("AAS access rules reference unknown FMI variables")
        variables = {
            name: _validated_override(name, permission, overrides[name])
            if name in overrides else permission
            for name, permission in variables.items()
        }

    canonical = json.dumps(
        {"version": POLICY_VERSION, "variables": variables},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {
        "policyVersion": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "policySource": source,
        "variables": variables,
    }
