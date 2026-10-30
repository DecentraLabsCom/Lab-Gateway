"""FMI access enforcement and stable public policy imports.

FMI defaults and AAS Part 4 rule compilation live in focused pure modules;
this module keeps the existing import surface for Gateway callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aas_part4_policy import (
    build_part4_access_rules,
    compile_part4_access_rules,
    fmi_interface_digest,
)
from fmi_variable_policy import (
    POLICY_VERSION,
    _PHASE_SET,
    build_effective_policy,
)
from fmi_ls_struct import normalize_fmi_ls_struct


class AccessDenied(Exception):
    """A requested variable operation is not allowed by the effective policy."""


def validate_writes(
    policy: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    phase: str,
) -> None:
    """Reject any value map containing a variable the consumer cannot write."""
    if phase not in _PHASE_SET:
        raise ValueError("unknown FMI write phase")
    if not isinstance(values, Mapping):
        raise AccessDenied
    variable_permissions = policy.get("variables")
    if not isinstance(variable_permissions, Mapping):
        raise AccessDenied
    for name in values:
        permission = variable_permissions.get(name)
        if not isinstance(name, str) or not isinstance(permission, Mapping):
            raise AccessDenied
        phases = permission.get("writeAt")
        if not isinstance(phases, list) or phase not in phases:
            raise AccessDenied


def validate_reads(policy: Mapping[str, Any], names: Any) -> None:
    """Reject explicit requests for values the reservation cannot read."""
    if names is None:
        return
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise AccessDenied
    variable_permissions = policy.get("variables")
    if not isinstance(variable_permissions, Mapping):
        raise AccessDenied
    for name in names:
        permission = variable_permissions.get(name)
        if not isinstance(permission, Mapping) or permission.get("read") is not True:
            raise AccessDenied


def validate_read_value_references(policy: Mapping[str, Any], value_references: Any) -> None:
    """Resolve FMI value references through authorized metadata before reads."""
    if not isinstance(value_references, list):
        raise AccessDenied
    raw_model_variables = policy.get("modelVariables")
    if not isinstance(raw_model_variables, list):
        raise AccessDenied
    references: dict[int, str] = {}
    ambiguous: set[int] = set()
    for variable in raw_model_variables:
        if not isinstance(variable, Mapping):
            continue
        value_reference = variable.get("valueReference")
        name = variable.get("name")
        if isinstance(value_reference, bool) or not isinstance(value_reference, int):
            continue
        if not isinstance(name, str) or not name:
            continue
        if value_reference in references and references[value_reference] != name:
            ambiguous.add(value_reference)
        else:
            references[value_reference] = name
    if any(
        isinstance(value_reference, bool)
        or not isinstance(value_reference, int)
        or value_reference in ambiguous
        or value_reference not in references
        for value_reference in value_references
    ):
        raise AccessDenied
    validate_reads(policy, [references[value_reference] for value_reference in value_references])


def visible_model_variables(
    policy: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return only variable descriptors needed for allowed reads or writes."""
    permissions = policy.get("variables")
    if not isinstance(permissions, Mapping):
        return []
    visible = []
    for variable in metadata.get("modelVariables", []):
        if not isinstance(variable, Mapping):
            continue
        name = variable.get("name")
        permission = permissions.get(name) if isinstance(name, str) else None
        if not isinstance(permission, Mapping):
            continue
        readable = permission.get("read") is True
        write_at = permission.get("writeAt")
        writable = isinstance(write_at, list) and bool(write_at)
        if readable or writable:
            visible.append(dict(variable))
    return visible


def filter_model_description(policy: Mapping[str, Any], payload: Any) -> Any:
    """Retain readable and writable variables in a realtime description reply."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("modelVariables"), list):
        return filter_fmi_values(policy, payload)
    filtered = dict(payload)
    safe_variables = visible_model_variables(policy, payload)
    for variable in safe_variables:
        name = variable.get("name")
        permission = policy.get("variables", {}).get(name, {})
        if permission.get("read") is not True:
            variable.pop("start", None)
    filtered["modelVariables"] = safe_variables
    raw_permissions = policy.get("variables")
    permissions = raw_permissions if isinstance(raw_permissions, Mapping) else {}
    readable_names = {
        name
        for name, permission in permissions.items()
        if isinstance(name, str) and isinstance(permission, Mapping) and permission.get("read") is True
    }
    fmi_ls_struct = normalize_fmi_ls_struct(
        payload.get("fmiLsStruct"),
        variable_names=readable_names,
    )
    if fmi_ls_struct is not None:
        filtered["fmiLsStruct"] = fmi_ls_struct
    else:
        filtered.pop("fmiLsStruct", None)
    return filtered


def filter_fmi_values(policy: Mapping[str, Any], payload: Any) -> Any:
    """Remove unreadable FMI values from nested Gateway/Executor responses."""
    permissions = policy.get("variables")
    if not isinstance(permissions, Mapping):
        return payload

    def visit(value: Any, parent_key: str | None = None) -> Any:
        if isinstance(value, Mapping):
            filtered: dict[str, Any] = {}
            output_map = parent_key in {"outputs", "modelVariables"}
            for key, item in value.items():
                if not isinstance(key, str):
                    continue
                permission = permissions.get(key)
                if isinstance(permission, Mapping) and permission.get("read") is not True:
                    continue
                if output_map and (not isinstance(permission, Mapping) or permission.get("read") is not True):
                    continue
                child = visit(item, key)
                if key in {"inputs", "parameters"} and isinstance(item, Mapping) and not child:
                    continue
                filtered[key] = child
            return filtered
        if isinstance(value, list):
            result = []
            for item in value:
                if parent_key == "outputVariables":
                    permission = permissions.get(item) if isinstance(item, str) else None
                    if not isinstance(permission, Mapping) or permission.get("read") is not True:
                        continue
                if isinstance(item, Mapping):
                    name = item.get("name")
                    permission = permissions.get(name) if isinstance(name, str) else None
                    if isinstance(permission, Mapping) and permission.get("read") is not True:
                        continue
                result.append(visit(item, parent_key))
            return result
        return value

    return visit(payload)


__all__ = [
    "AccessDenied",
    "POLICY_VERSION",
    "build_effective_policy",
    "build_part4_access_rules",
    "compile_part4_access_rules",
    "fmi_interface_digest",
    "filter_model_description",
    "filter_fmi_values",
    "validate_read_value_references",
    "validate_reads",
    "validate_writes",
    "visible_model_variables",
]
