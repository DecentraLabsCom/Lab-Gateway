"""FMI-derived variable permissions and fail-closed policy helpers.

This module deliberately contains no Gateway, BaSyx, or Station I/O.  Routers
use the same compiled policy for request validation and response filtering.
"""

from __future__ import annotations

import hashlib
import json
import math
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
_MAX_POLICY_BYTES = 1_048_576
_MAX_POLICY_RULES = 20_000
_MAX_RULE_OBJECTS = 20_000
_MAX_EXPANDED_DEFINITION_ITEMS = 20_000
_MAX_FORMULA_DEPTH = 12
_MAX_FORMULA_NODES = 128
_IDSHORT_UNSAFE_RE = re.compile(r"[^a-zA-Z0-9]+")


class AccessDenied(Exception):
    """A requested variable operation is not allowed by the effective policy."""


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


def _sanitize_idshort(value: str) -> str:
    sanitized = _IDSHORT_UNSAFE_RE.sub("_", value).strip("_") or "Unit"
    return f"u{sanitized}" if sanitized[0].isdigit() else sanitized


def _fmi_port(causality: str) -> str | None:
    return {
        "input": "Input",
        "output": "Output",
        "parameter": "Parameter",
        "calculatedParameter": "Parameter",
        "structuralParameter": "Parameter",
        "independent": "Internal",
    }.get(causality)


def fmi_interface_digest(metadata: Mapping[str, Any]) -> str:
    """Hash the FMI fields that determine AAS variable references and access."""
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("modelVariables"), list):
        raise ValueError("FMU variable metadata is invalid")
    variables = []
    for variable in metadata["modelVariables"]:
        if not isinstance(variable, Mapping):
            raise ValueError("FMU variable metadata is invalid")
        variables.append({
            field: variable.get(field)
            for field in ("name", "causality", "variability", "type", "valueReference", "dimensions")
            if field in variable
        })
    variables.sort(key=lambda variable: str(variable.get("name") or ""))
    canonical = json.dumps(variables, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _part4_object_paths(metadata: Mapping[str, Any], submodel_id: str | None) -> dict[str, str]:
    raw_variables = metadata.get("modelVariables")
    if not isinstance(raw_variables, list) or len(raw_variables) > _MAX_VARIABLES:
        raise ValueError("FMU variable metadata is invalid")
    paths: dict[str, str] = {}
    names: set[str] = set()
    for variable in raw_variables:
        if not isinstance(variable, Mapping):
            raise ValueError("FMU variable metadata is invalid")
        name = variable.get("name")
        if not isinstance(name, str) or not name or len(name) > _MAX_VARIABLE_NAME_LENGTH or name in names:
            raise ValueError("FMU variable names are invalid or ambiguous")
        names.add(name)
        port = _fmi_port(str(variable.get("causality") or "local"))
        if port is None:
            continue
        path = f"SimulationModel.Ports.{port}.{_sanitize_idshort(name)}"
        if path in paths:
            raise ValueError("AAS idShort collision makes an FMI variable reference ambiguous")
        paths[path] = name
    return paths


def _referable_name(
    value: Any,
    submodel_id: str | None,
    paths: Mapping[str, str],
    *,
    allowed_submodel_ids: set[str] | None = None,
) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("AAS access policy contains an invalid variable reference")
    prefix = "$sme("
    if not value.startswith(prefix):
        raise ValueError("AAS access policy must use exact AAS Referable objects")
    try:
        referenced_submodel, end = json.JSONDecoder().raw_decode(value, len(prefix))
    except (TypeError, ValueError):
        raise ValueError("AAS access policy contains an invalid submodel reference")
    if value[end:end + 2] != ").":
        raise ValueError("AAS access policy contains an invalid submodel reference")
    path = value[end + 2:]
    if (
        (submodel_id is not None and referenced_submodel != submodel_id)
        or (allowed_submodel_ids is not None and referenced_submodel not in allowed_submodel_ids)
        or path not in paths
    ):
        raise ValueError("AAS access policy references an unknown FMI variable")
    return paths[path]


def build_part4_access_rules(metadata: Mapping[str, Any], submodel_id: str) -> dict[str, Any]:
    """Build the strict IDTA Part 4 JSON allow-list for FMI-supported rights.

    AAS Part 4 defaults to deny. The Gateway separately requires an active
    reservation, so generated rules can use an empty subject-attribute list and
    a true formula while granting only rights supported by FMI/runtime.
    """
    if not isinstance(submodel_id, str) or not submodel_id or len(submodel_id) > 2048:
        raise ValueError("AAS simulation submodel ID is invalid")
    defaults = build_effective_policy(metadata)["variables"]
    paths = _part4_object_paths(metadata, submodel_id)
    read_objects: list[dict[str, str]] = []
    update_objects: list[dict[str, str]] = []
    for path, name in sorted(paths.items()):
        permissions = defaults[name]
        if permissions["read"]:
            read_objects.append({"REFERABLE": f"$sme({json.dumps(submodel_id)}).{path}"})
        if permissions["writeAt"]:
            update_objects.append({"REFERABLE": f"$sme({json.dumps(submodel_id)}).{path}"})

    rules = []
    for right, objects in (("READ", read_objects), ("UPDATE", update_objects)):
        if objects:
            rules.append({
                "ACL": {"ATTRIBUTES": [], "RIGHTS": [right], "ACCESS": "ALLOW"},
                "OBJECTS": objects,
                "FORMULA": {"$boolean": True},
            })
    document = {"AllAccessPermissionRules": {"rules": rules}}
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(rules) > _MAX_POLICY_RULES or len(encoded) > _MAX_POLICY_BYTES:
        raise ValueError("AAS access policy exceeds its size limit")
    return document


def _formula_claims(formula: Any) -> set[str]:
    claims: set[str] = set()
    node_count = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_FORMULA_NODES or depth > _MAX_FORMULA_DEPTH or not isinstance(node, Mapping) or len(node) != 1:
            raise ValueError("AAS access policy formula is invalid or too complex")
        operator, operand = next(iter(node.items()))
        if operator == "$boolean":
            if not isinstance(operand, bool):
                raise ValueError("AAS access policy formula has an invalid boolean")
        elif operator == "$attribute":
            if not isinstance(operand, Mapping) or set(operand) != {"CLAIM"}:
                raise ValueError("AAS access policy supports only authenticated CLAIM attributes")
            claim = operand["CLAIM"]
            if not isinstance(claim, str) or not claim or len(claim) > 128:
                raise ValueError("AAS access policy claim name is invalid")
            claims.add(claim)
        elif operator == "$strVal":
            if not isinstance(operand, str) or len(operand) > 4096:
                raise ValueError("AAS access policy string literal is invalid")
        elif operator == "$numVal":
            if isinstance(operand, bool) or not isinstance(operand, (int, float)) or not math.isfinite(float(operand)):
                raise ValueError("AAS access policy numeric literal is invalid")
        elif operator == "$boolVal":
            if not isinstance(operand, bool):
                raise ValueError("AAS access policy boolean literal is invalid")
        elif operator in {"$eq", "$ne"}:
            if not isinstance(operand, list) or len(operand) != 2:
                raise ValueError("AAS access policy comparison is invalid")
            visit(operand[0], depth + 1)
            visit(operand[1], depth + 1)
        elif operator in {"$and", "$or"}:
            if not isinstance(operand, list) or len(operand) < 2 or len(operand) > 32:
                raise ValueError("AAS access policy boolean expression is invalid")
            for child in operand:
                visit(child, depth + 1)
        else:
            raise ValueError("AAS access policy uses an unsupported formula operator")

    visit(formula, 0)
    return claims


_MISSING = object()


def _evaluate_formula(formula: Any, claims: Mapping[str, Any], allowed_claims: set[str]) -> Any:
    operator, operand = next(iter(formula.items()))
    if operator == "$boolean":
        return operand
    if operator == "$attribute":
        name = operand["CLAIM"]
        value = claims.get(name, _MISSING)
        return value if isinstance(value, bool) else value
    if operator in {"$strVal", "$numVal", "$boolVal"}:
        return operand
    if operator in {"$eq", "$ne"}:
        left = _evaluate_formula(operand[0], claims, allowed_claims)
        right = _evaluate_formula(operand[1], claims, allowed_claims)
        if left is _MISSING or right is _MISSING or type(left) is not type(right):
            return False
        return left == right if operator == "$eq" else left != right
    values = [_evaluate_formula(child, claims, allowed_claims) for child in operand]
    if any(not isinstance(value, bool) for value in values):
        raise ValueError("AAS access policy boolean operators require boolean operands")
    return all(values) if operator == "$and" else any(values)


def _definition_map(
    value: Any,
    *,
    field: str,
    allowed_fields: set[str],
) -> dict[str, Mapping[str, Any]]:
    if value is _MISSING:
        return {}
    if not isinstance(value, list) or len(value) > _MAX_POLICY_RULES:
        raise ValueError(f"AAS Part 4 {field} definitions are invalid")
    definitions: dict[str, Mapping[str, Any]] = {}
    for definition in value:
        if (
            not isinstance(definition, Mapping)
            or "name" not in definition
            or set(definition) - allowed_fields
        ):
            raise ValueError(f"AAS Part 4 {field} definition is invalid")
        name = definition.get("name")
        if not isinstance(name, str) or not name or len(name) > 128 or name in definitions:
            raise ValueError(f"AAS Part 4 {field} definition name is invalid or duplicated")
        definitions[name] = definition
    return definitions


def _definition_references(value: Any, *, key: str, maximum: int = 64) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"AAS Part 4 {key} references are invalid")
    references = []
    for reference in value:
        if not isinstance(reference, str) or not reference or len(reference) > 128:
            raise ValueError(f"AAS Part 4 {key} reference is invalid")
        references.append(reference)
    if len(references) != len(set(references)):
        raise ValueError(f"AAS Part 4 {key} references contain duplicates")
    return references


def _expand_attribute_groups(
    definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    resolved: dict[str, list[dict[str, str]]] = {}
    visiting: set[str] = set()
    total_expanded_items = 0

    def expand(name: str, depth: int = 0) -> list[dict[str, str]]:
        nonlocal total_expanded_items
        if name in resolved:
            return resolved[name]
        if name not in definitions or name in visiting or depth > _MAX_FORMULA_DEPTH:
            raise ValueError("AAS Part 4 attribute group is missing, cyclic, or too deep")
        visiting.add(name)
        definition = definitions[name]
        keys = set(definition) - {"name"}
        if not keys or keys - {"attributes", "USEATTRIBUTES"}:
            raise ValueError("AAS Part 4 attribute group is invalid")
        attributes: list[dict[str, str]] = []
        if "attributes" in definition:
            raw_attributes = definition["attributes"]
            if not isinstance(raw_attributes, list) or len(raw_attributes) > 64:
                raise ValueError("AAS Part 4 attributes are invalid")
            for attribute in raw_attributes:
                if not isinstance(attribute, Mapping) or set(attribute) != {"CLAIM"}:
                    raise ValueError("AAS Part 4 supports only authenticated CLAIM attributes")
                claim = attribute["CLAIM"]
                if not isinstance(claim, str) or not claim or len(claim) > 128:
                    raise ValueError("AAS Part 4 claim name is invalid")
                attributes.append({"CLAIM": claim})
                if len(attributes) > _MAX_EXPANDED_DEFINITION_ITEMS:
                    raise ValueError("AAS Part 4 attribute groups expand beyond the size limit")
        if "USEATTRIBUTES" in definition:
            for reference in _definition_references(definition["USEATTRIBUTES"], key="USEATTRIBUTES"):
                nested = expand(reference, depth + 1)
                if len(attributes) + len(nested) > _MAX_EXPANDED_DEFINITION_ITEMS:
                    raise ValueError("AAS Part 4 attribute groups expand beyond the size limit")
                attributes.extend(nested)
        claims = [attribute["CLAIM"] for attribute in attributes]
        if len(claims) != len(set(claims)):
            raise ValueError("AAS Part 4 attribute group contains duplicate claims")
        visiting.remove(name)
        resolved[name] = attributes
        total_expanded_items += len(attributes)
        if total_expanded_items > _MAX_EXPANDED_DEFINITION_ITEMS:
            raise ValueError("AAS Part 4 attribute definitions exceed the expansion limit")
        return attributes

    for name in definitions:
        expand(name)
    return resolved


def _expand_object_groups(
    definitions: Mapping[str, Mapping[str, Any]],
    *,
    submodel_id: str | None,
    paths: Mapping[str, str],
    allowed_submodel_ids: set[str] | None,
) -> dict[str, list[str]]:
    resolved: dict[str, list[str]] = {}
    visiting: set[str] = set()
    total_expanded_items = 0

    def expand(name: str, depth: int = 0) -> list[str]:
        nonlocal total_expanded_items
        if name in resolved:
            return resolved[name]
        if name not in definitions or name in visiting or depth > _MAX_FORMULA_DEPTH:
            raise ValueError("AAS Part 4 object group is missing, cyclic, or too deep")
        visiting.add(name)
        definition = definitions[name]
        keys = set(definition) - {"name"}
        if not keys or keys - {"objects", "USEOBJECTS"}:
            raise ValueError("AAS Part 4 object group is invalid")
        names: list[str] = []
        if "objects" in definition:
            objects = definition["objects"]
            if not isinstance(objects, list) or len(objects) > _MAX_RULE_OBJECTS:
                raise ValueError("AAS Part 4 object group is invalid")
            for obj in objects:
                if not isinstance(obj, Mapping) or set(obj) != {"REFERABLE"}:
                    raise ValueError("AAS Part 4 profile requires exact REFERABLE objects")
                names.append(_referable_name(
                    obj["REFERABLE"],
                    submodel_id,
                    paths,
                    allowed_submodel_ids=allowed_submodel_ids,
                ))
                if len(names) > _MAX_EXPANDED_DEFINITION_ITEMS:
                    raise ValueError("AAS Part 4 object groups expand beyond the size limit")
        if "USEOBJECTS" in definition:
            for reference in _definition_references(definition["USEOBJECTS"], key="USEOBJECTS"):
                nested = expand(reference, depth + 1)
                if len(names) + len(nested) > _MAX_EXPANDED_DEFINITION_ITEMS:
                    raise ValueError("AAS Part 4 object groups expand beyond the size limit")
                names.extend(nested)
        if len(names) > _MAX_RULE_OBJECTS or len(names) != len(set(names)):
            raise ValueError("AAS Part 4 object group is too large or contains duplicate variables")
        visiting.remove(name)
        resolved[name] = names
        total_expanded_items += len(names)
        if total_expanded_items > _MAX_EXPANDED_DEFINITION_ITEMS:
            raise ValueError("AAS Part 4 object definitions exceed the expansion limit")
        return names

    for name in definitions:
        expand(name)
    return resolved


def _resolve_part4_acl(
    acl: Any,
    *,
    attribute_groups: Mapping[str, list[dict[str, str]]],
) -> tuple[set[str], set[str], str]:
    if not isinstance(acl, Mapping) or set(acl) - {"ATTRIBUTES", "USEATTRIBUTES", "RIGHTS", "ACCESS"}:
        raise ValueError("AAS Part 4 ACL is invalid")
    if "RIGHTS" not in acl or "ACCESS" not in acl or not ({"ATTRIBUTES", "USEATTRIBUTES"} & set(acl)):
        raise ValueError("AAS Part 4 ACL is incomplete")
    rights = acl["RIGHTS"]
    supported_rights = {"READ", "UPDATE"}
    if not isinstance(rights, list) or not rights or any(not isinstance(right, str) for right in rights):
        raise ValueError("AAS Part 4 profile supports only READ and UPDATE rights")
    if len(rights) != len(set(rights)) or any(right not in supported_rights for right in rights):
        raise ValueError("AAS Part 4 profile supports only READ and UPDATE rights")
    access = acl["ACCESS"]
    if not isinstance(access, str) or access not in {"ALLOW", "DISABLED"}:
        raise ValueError("AAS Part 4 access type is invalid")

    attributes: list[dict[str, str]] = []
    if "ATTRIBUTES" in acl:
        raw_attributes = acl["ATTRIBUTES"]
        if not isinstance(raw_attributes, list) or len(raw_attributes) > 64:
            raise ValueError("AAS Part 4 ACL attributes are invalid")
        for attribute in raw_attributes:
            if not isinstance(attribute, Mapping) or set(attribute) != {"CLAIM"}:
                raise ValueError("AAS Part 4 profile supports only authenticated CLAIM attributes")
            claim = attribute["CLAIM"]
            if not isinstance(claim, str) or not claim or len(claim) > 128:
                raise ValueError("AAS Part 4 ACL claim is invalid")
            attributes.append({"CLAIM": claim})
    if "USEATTRIBUTES" in acl:
        reference = acl["USEATTRIBUTES"]
        if not isinstance(reference, str) or reference not in attribute_groups:
            raise ValueError("AAS Part 4 ACL references an unknown attribute group")
        attributes.extend(attribute_groups[reference])
    claims = [attribute["CLAIM"] for attribute in attributes]
    if len(claims) != len(set(claims)):
        raise ValueError("AAS Part 4 ACL contains duplicate claims")
    return set(claims), set(rights), access


def compile_part4_access_rules(
    document: Any,
    metadata: Mapping[str, Any],
    submodel_id: str | None,
    *,
    declared_interface_digest: str | None,
    claims: Mapping[str, Any],
    source: str = "aas-provider",
    allowed_submodel_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Compile the supported, fail-closed IDTA Part 4 JSON profile into FMI rights.

    This profile supports exact variable REFERABLE objects, reusable
    DEFATTRIBUTES/DEFACLS/DEFOBJECTS/DEFFORMULAS definitions, READ/UPDATE
    ALLOW rules, DISABLED rules, and boolean/equality formulas over verified
    scalar claims. Unsupported Part 4 objects, rights, filters and operators
    are rejected rather than silently ignored.
    """
    if not isinstance(claims, Mapping):
        raise ValueError("Authenticated reservation claims are invalid")
    actual_digest = fmi_interface_digest(metadata)
    if declared_interface_digest is not None and (
        not isinstance(declared_interface_digest, str)
        or declared_interface_digest != actual_digest
    ):
        raise ValueError("AAS FMI access policy is stale for the current FMU interface")
    if source == "aas-generated" and declared_interface_digest is None:
        raise ValueError("Generated AAS FMI access policy has no interface digest")
    expected = build_effective_policy(metadata)["variables"]
    paths = _part4_object_paths(metadata, submodel_id)
    if not isinstance(document, Mapping) or set(document) != {"AllAccessPermissionRules"}:
        raise ValueError("AAS Part 4 access rule document is invalid")
    rules_container = document["AllAccessPermissionRules"]
    definition_keys = {"DEFATTRIBUTES", "DEFACLS", "DEFOBJECTS", "DEFFORMULAS", "rules"}
    if not isinstance(rules_container, Mapping) or set(rules_container) - definition_keys:
        raise ValueError("AAS Part 4 access rule document is invalid")
    rules = rules_container.get("rules")
    if not isinstance(rules, list) or len(rules) > _MAX_POLICY_RULES:
        raise ValueError("AAS Part 4 access rule list is invalid")

    attribute_definitions = _definition_map(
        rules_container.get("DEFATTRIBUTES", _MISSING),
        field="DEFATTRIBUTES",
        allowed_fields={"name", "attributes", "USEATTRIBUTES"},
    )
    attribute_groups = _expand_attribute_groups(attribute_definitions)

    acl_definitions = _definition_map(
        rules_container.get("DEFACLS", _MISSING),
        field="DEFACLS",
        allowed_fields={"name", "acl"},
    )
    acl_groups: dict[str, tuple[set[str], set[str], str]] = {}
    for name, definition in acl_definitions.items():
        if set(definition) != {"name", "acl"}:
            raise ValueError("AAS Part 4 ACL definition is invalid")
        acl_groups[name] = _resolve_part4_acl(definition["acl"], attribute_groups=attribute_groups)

    object_definitions = _definition_map(
        rules_container.get("DEFOBJECTS", _MISSING),
        field="DEFOBJECTS",
        allowed_fields={"name", "objects", "USEOBJECTS"},
    )
    object_groups = _expand_object_groups(
        object_definitions,
        submodel_id=submodel_id,
        paths=paths,
        allowed_submodel_ids=allowed_submodel_ids,
    )

    formula_definitions = _definition_map(
        rules_container.get("DEFFORMULAS", _MISSING),
        field="DEFFORMULAS",
        allowed_fields={"name", "formula"},
    )
    formula_groups: dict[str, Any] = {}
    for name, definition in formula_definitions.items():
        if set(definition) != {"name", "formula"}:
            raise ValueError("AAS Part 4 formula definition is invalid")
        _formula_claims(definition["formula"])
        formula_groups[name] = definition["formula"]

    granted = {name: {"read": False, "writeAt": []} for name in expected}
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > _MAX_POLICY_BYTES:
        raise ValueError("AAS access policy exceeds its size limit")

    for rule in rules:
        rule_keys = {"ACL", "USEACL", "OBJECTS", "USEOBJECTS", "FORMULA", "USEFORMULA"}
        if not isinstance(rule, Mapping) or set(rule) - rule_keys:
            raise ValueError("AAS Part 4 rule uses unsupported fields")
        if ("ACL" in rule) == ("USEACL" in rule):
            raise ValueError("AAS Part 4 rule must specify exactly one ACL")
        if ("FORMULA" in rule) == ("USEFORMULA" in rule):
            raise ValueError("AAS Part 4 rule must specify exactly one formula")
        if not ({"OBJECTS", "USEOBJECTS"} & set(rule)):
            raise ValueError("AAS Part 4 rule must specify objects")

        if "ACL" in rule:
            allowed_claims, rights, access = _resolve_part4_acl(
                rule["ACL"],
                attribute_groups=attribute_groups,
            )
        else:
            acl_name = rule["USEACL"]
            if not isinstance(acl_name, str) or acl_name not in acl_groups:
                raise ValueError("AAS Part 4 rule references an unknown ACL")
            allowed_claims, rights, access = acl_groups[acl_name]

        if "FORMULA" in rule:
            formula = rule["FORMULA"]
        else:
            formula_name = rule["USEFORMULA"]
            if not isinstance(formula_name, str) or formula_name not in formula_groups:
                raise ValueError("AAS Part 4 rule references an unknown formula")
            formula = formula_groups[formula_name]
        referenced_claims = _formula_claims(formula)

        names: list[str] = []
        if "OBJECTS" in rule:
            objects = rule["OBJECTS"]
            if not isinstance(objects, list) or len(objects) > _MAX_RULE_OBJECTS:
                raise ValueError("AAS Part 4 rule objects are invalid")
            for obj in objects:
                if not isinstance(obj, Mapping) or set(obj) != {"REFERABLE"}:
                    raise ValueError("AAS Part 4 profile requires exact REFERABLE objects")
                names.append(_referable_name(
                    obj["REFERABLE"],
                    submodel_id,
                    paths,
                    allowed_submodel_ids=allowed_submodel_ids,
                ))
        if "USEOBJECTS" in rule:
            for object_group in _definition_references(rule["USEOBJECTS"], key="USEOBJECTS"):
                if object_group not in object_groups:
                    raise ValueError("AAS Part 4 rule references an unknown object group")
                names.extend(object_groups[object_group])
        if not names or len(names) > _MAX_RULE_OBJECTS or len(names) != len(set(names)):
            raise ValueError("AAS Part 4 rule objects are empty, too large, or duplicated")

        # Part 4 says a DISABLED ACL is ignored. Validate its references and
        # shape above, but never grant rights from it.
        if access == "DISABLED":
            continue

        # Validate all potential grants, even when the current user's formula
        # is false. A rule may never authorize more than the FMU/runtime can.
        for name in names:
            if "READ" in rights and not expected[name]["read"]:
                raise ValueError("AAS policy cannot grant reads unsupported by FMI")
            if "UPDATE" in rights and not expected[name]["writeAt"]:
                raise ValueError("AAS policy cannot grant writes unsupported by FMI")

        # Per Part 4, a formula referencing an attribute absent from its ACL
        # evaluates false. Never infer that missing attribute as true.
        formula_result = (
            _evaluate_formula(formula, claims, allowed_claims)
            if referenced_claims.issubset(allowed_claims)
            else False
        )
        if not isinstance(formula_result, bool):
            raise ValueError("AAS access policy formula must evaluate to a boolean")
        if not formula_result:
            continue
        for name in names:
            if "READ" in rights:
                granted[name]["read"] = True
            if "UPDATE" in rights:
                granted[name]["writeAt"] = list(expected[name]["writeAt"])

    if source not in {"aas-generated", "aas-provider"}:
        raise ValueError("AAS access policy source is invalid")
    policy = build_effective_policy(metadata, overrides=granted, source=source)
    policy["interfaceDigest"] = actual_digest
    return policy


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
