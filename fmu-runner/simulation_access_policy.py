"""FMI access enforcement and stable public policy imports.

FMI defaults and AAS Part 4 rule compilation live in focused pure modules;
this module keeps the existing import surface for Gateway callers.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from aas_part4_policy import (
    available_execution_interfaces,
    build_part4_access_rules,
    compile_part4_access_rules,
    default_authorized_execution_interfaces,
    fmi_interface_digest,
    normalize_authorized_execution_interfaces,
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
    phase: str | Collection[str],
) -> None:
    """Reject values not authorized in any requested FMI write phase."""
    phases_to_accept = {phase} if isinstance(phase, str) else set(phase)
    if not phases_to_accept or not phases_to_accept.issubset(_PHASE_SET):
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
        if not isinstance(phases, list) or not phases_to_accept.intersection(phases):
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
    *,
    preserve_local_value_references: Collection[int] | None = None,
) -> list[dict[str, Any]]:
    """Return accessible variables plus required local dimension descriptors.

    Preserving an immutable descriptor for array-shape metadata does not add
    read or write permissions for that variable.
    """
    permissions = policy.get("variables")
    if not isinstance(permissions, Mapping):
        permissions = {}
    preserved_references = preserve_local_value_references or ()
    visible = []
    for variable in metadata.get("modelVariables", []):
        if not isinstance(variable, Mapping):
            continue
        name = variable.get("name")
        permission = permissions.get(name) if isinstance(name, str) else None
        if not isinstance(permission, Mapping):
            permission = {}
        readable = permission.get("read") is True
        write_at = permission.get("writeAt")
        writable = isinstance(write_at, list) and bool(write_at)
        reference = variable.get("valueReference")
        required_local_dimension_constant = (
            str(variable.get("causality") or "local").lower() == "local"
            and str(variable.get("type") or "").lower() == "uint64"
            and str(variable.get("variability") or "").lower() == "constant"
            and type(reference) is int
            and reference in preserved_references
        )
        if readable or writable or required_local_dimension_constant:
            visible.append(dict(variable))
    return visible


def _visible_fmi_model_structure(
    raw_structure: Any,
    variables: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Keep only ModelStructure entries whose variables are visible to this reservation."""
    if not isinstance(raw_structure, Mapping):
        return {}
    allowed_names = {item.get("name") for item in variables if isinstance(item.get("name"), str)}
    name_by_reference = {
        str(item.get("valueReference")): item.get("name")
        for item in variables
        if isinstance(item.get("name"), str) and item.get("valueReference") is not None
    }
    result: dict[str, list[dict[str, Any]]] = {}
    for section in ("outputs", "derivatives", "clockedStates", "initialUnknowns", "eventIndicators"):
        raw_entries = raw_structure.get(section)
        if not isinstance(raw_entries, list):
            continue
        safe_entries: list[dict[str, Any]] = []
        for entry in raw_entries[:100_000]:
            if not isinstance(entry, Mapping):
                continue
            reference = entry.get("valueReference")
            name = entry.get("name") if isinstance(entry.get("name"), str) else None
            if name not in allowed_names:
                name = name_by_reference.get(str(reference))
            state_name = entry.get("stateName") if isinstance(entry.get("stateName"), str) else None
            if state_name not in allowed_names:
                state_name = None
            if not name and not state_name:
                continue
            safe_entry: dict[str, Any] = {}
            if name:
                safe_entry["name"] = name[:512]
            if state_name:
                safe_entry["stateName"] = state_name[:512]

            raw_dependencies = entry.get("dependencies")
            raw_names = entry.get("dependencyNames")
            raw_kinds = entry.get("dependenciesKind")
            dependency_count = max(
                len(raw_names) if isinstance(raw_names, list) else 0,
                len(raw_dependencies) if isinstance(raw_dependencies, list) else 0,
            )
            selected: list[tuple[str, str | None]] = []
            for index in range(min(dependency_count, 100_000)):
                dependency_name = raw_names[index] if isinstance(raw_names, list) and index < len(raw_names) else None
                dependency_reference = raw_dependencies[index] if isinstance(raw_dependencies, list) and index < len(raw_dependencies) else None
                if dependency_name not in allowed_names:
                    dependency_name = name_by_reference.get(str(dependency_reference))
                if not isinstance(dependency_name, str) or dependency_name not in allowed_names:
                    continue
                kind = raw_kinds[index] if isinstance(raw_kinds, list) and index < len(raw_kinds) else None
                selected.append((dependency_name[:512], kind[:64] if isinstance(kind, str) else None))
                if len(selected) >= 4096:
                    break
            if selected:
                safe_entry["dependencyNames"] = [dependency for dependency, _kind in selected]
                kinds = [kind for _dependency, kind in selected]
                if all(kind is not None for kind in kinds):
                    safe_entry["dependenciesKind"] = kinds
            safe_entries.append(safe_entry)
        if safe_entries:
            result[section] = safe_entries
    return result


def filter_model_description(
    policy: Mapping[str, Any],
    payload: Any,
    *,
    include_proxy_dae_selector: bool = False,
    include_proxy_model_exchange: bool = False,
    preserve_local_value_references: Collection[int] | None = None,
) -> Any:
    """Retain accessible variables and explicitly required dimension constants."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("modelVariables"), list):
        return filter_fmi_values(policy, payload)
    filtered = dict(payload)
    raw_fmi_ls_dae = payload.get("fmiLsDae")
    # Keep the execution capability flag, but do not publish solver-equation
    # declarations from the executor's private FMI-LS-DAE manifest.
    filtered.pop("fmiLsDae", None)
    filtered.pop("fmiLsDaeIssue", None)
    raw_permissions = policy.get("variables")
    permissions = raw_permissions if isinstance(raw_permissions, Mapping) else {}
    safe_variables = (
        [dict(variable) for variable in payload.get("modelVariables", []) if isinstance(variable, Mapping)]
        if include_proxy_model_exchange
        else visible_model_variables(
            policy,
            payload,
            preserve_local_value_references=preserve_local_value_references,
        )
    )
    for variable in safe_variables:
        name = variable.get("name")
        permission = permissions.get(name) if isinstance(name, str) else None
        if not isinstance(permission, Mapping):
            permission = {}
        reference = variable.get("valueReference")
        required_local_dimension_constant = (
            str(variable.get("causality") or "local").lower() == "local"
            and str(variable.get("type") or "").lower() == "uint64"
            and str(variable.get("variability") or "").lower() == "constant"
            and type(reference) is int
            and reference in (preserve_local_value_references or ())
        )
        if (
            not include_proxy_model_exchange
            and permission.get("read") is not True
            and not required_local_dimension_constant
        ):
            variable.pop("start", None)
    filtered["modelVariables"] = safe_variables
    if not include_proxy_model_exchange:
        safe_structure = _visible_fmi_model_structure(payload.get("modelStructure"), safe_variables)
        if safe_structure:
            filtered["modelStructure"] = safe_structure
        else:
            filtered.pop("modelStructure", None)
    if include_proxy_model_exchange:
        model_structure = payload.get("modelStructure")
        if not isinstance(model_structure, Mapping):
            raise ValueError("Model Exchange metadata is missing FMI ModelStructure")
        filtered["modelStructure"] = dict(model_structure)
        for key in ("numberOfContinuousStates", "numberOfEventIndicators", "modelExchangeCapabilities"):
            if key in payload:
                filtered[key] = payload[key]
        raw_authorized_interfaces = policy.get("authorizedExecutionInterfaces")
        if isinstance(raw_authorized_interfaces, list):
            filtered["authorizedExecutionInterfaces"] = list(raw_authorized_interfaces)
        if isinstance(raw_fmi_ls_dae, Mapping):
            # ME authorization is the explicit provider grant for publishing
            # the equation interface. Variable writes remain checked against
            # the AAS variable policy by the Gateway.
            filtered["fmiLsDae"] = dict(raw_fmi_ls_dae)
    if include_proxy_dae_selector and not include_proxy_model_exchange and isinstance(raw_fmi_ls_dae, Mapping):
        selector_name = raw_fmi_ls_dae.get("enableDAEParameter")
        selector_permission = permissions.get(selector_name) if isinstance(selector_name, str) else None
        selector_is_visible = any(
            variable.get("name") == selector_name
            for variable in safe_variables
        )
        selector_write_phases = (
            selector_permission.get("writeAt")
            if isinstance(selector_permission, Mapping)
            else None
        )
        if (
            selector_is_visible
            and isinstance(selector_write_phases, list)
            and "configuration" in selector_write_phases
            and "reconfiguration" in selector_write_phases
        ):
            # Proxy generation needs the selector name to emit its legal FMI
            # interface. Keep this private summary out of normal describe and
            # browser-facing metadata responses.
            filtered["fmiLsDae"] = {"enableDAEParameter": selector_name}
    readable_names = [
        name
        for name, permission in permissions.items()
        if isinstance(name, str) and isinstance(permission, Mapping) and permission.get("read") is True
    ]
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
                # Checkpoint references are opaque signed tokens, not FMI
                # variable maps. Preserve them byte-for-byte through the
                # variable read policy so names inside the token cannot be
                # mistaken for model variables.
                if parent_key is None and key == "checkpoint":
                    filtered[key] = item
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
    "available_execution_interfaces",
    "build_effective_policy",
    "build_part4_access_rules",
    "compile_part4_access_rules",
    "default_authorized_execution_interfaces",
    "fmi_interface_digest",
    "filter_model_description",
    "filter_fmi_values",
    "normalize_authorized_execution_interfaces",
    "validate_read_value_references",
    "validate_reads",
    "validate_writes",
    "visible_model_variables",
]
