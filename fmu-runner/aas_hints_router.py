from typing import Any

from fastapi import APIRouter, HTTPException


_SCENE_VARIABLE_FIELDS = (
    "name", "type", "causality", "variability", "description", "displayName",
    "unit", "displayUnit", "quantity", "min", "max", "dimensions", "enumItems",
    "declaredType",
)


def _scene_binding_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Project only FMI fields needed by the provider-side GLB binding editor."""
    raw_variables = metadata.get("modelVariables")
    variables = []
    if isinstance(raw_variables, list):
        for variable in raw_variables:
            if not isinstance(variable, dict) or variable.get("causality") not in {"input", "output"}:
                continue
            item = {
                field: variable[field]
                for field in _SCENE_VARIABLE_FIELDS
                if field in variable and variable[field] is not None
            }
            if isinstance(item.get("name"), str) and item["name"] and len(item["name"]) <= 512:
                variables.append(item)
            if len(variables) >= 4096:
                break

    input_names = {
        variable["name"] for variable in variables if variable.get("causality") == "input"
    }
    output_names = {
        variable["name"] for variable in variables if variable.get("causality") == "output"
    }
    raw_structure = metadata.get("modelStructure")
    raw_outputs = raw_structure.get("outputs") if isinstance(raw_structure, dict) else None
    output_dependencies = []
    if isinstance(raw_outputs, list):
        for entry in raw_outputs[:4096]:
            if not isinstance(entry, dict) or entry.get("name") not in output_names:
                continue
            dependencies = entry.get("dependencyNames")
            if not isinstance(dependencies, list):
                continue
            names = list(dict.fromkeys(
                name for name in dependencies if isinstance(name, str) and name in input_names
            ))[:256]
            if names:
                output_dependencies.append({"name": entry["name"], "dependencyNames": names})

    raw_units = metadata.get("unitDefinitions")
    units = []
    if isinstance(raw_units, list):
        for raw_unit in raw_units[:1024]:
            if not isinstance(raw_unit, dict) or not isinstance(raw_unit.get("name"), str):
                continue
            unit = {"name": raw_unit["name"][:256]}
            base = raw_unit.get("baseUnit")
            if isinstance(base, dict):
                unit["baseUnit"] = {
                    field: base[field]
                    for field in ("kg", "m", "s", "A", "K", "mol", "cd", "rad", "factor", "offset")
                    if isinstance(base.get(field), (int, float)) and not isinstance(base.get(field), bool)
                }
            units.append(unit)

    return {
        "modelVariables": variables,
        "modelStructure": {"outputs": output_dependencies},
        "unitDefinitions": units,
        "variablesTruncated": isinstance(raw_variables, list) and len(raw_variables) > len(variables),
    }


def create_aas_hints_router(
    *,
    resolve_fmu_path: Any,
    read_model_description: Any,
    normalize_xml_value: Any,
    logger: Any,
    get_model_metadata: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/aas-admin/fmu/{access_key}/hints")
    async def aas_hints_fmu(access_key: str):
        if get_model_metadata is not None:
            try:
                metadata = await get_model_metadata(access_key)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(
                    "Cannot read FMU metadata for %s",
                    str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                    type(exc).__name__,
                )
                raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc
            if not isinstance(metadata, dict):
                raise HTTPException(status_code=422, detail="FMU metadata response is invalid")
            hints = {
                field: value
                for field, value in (
                    ("description", metadata.get("description")),
                    ("license", metadata.get("license")),
                    ("author", metadata.get("author")),
                    ("version", metadata.get("version")),
                    ("generationTool", metadata.get("generationTool")),
                )
                if isinstance(value, str) and value.strip()
            }
            hints["visualizationMetadata"] = _scene_binding_metadata(metadata)
            return hints

        fmu_path = resolve_fmu_path(access_key)
        try:
            model_description = read_model_description(fmu_path)
        except Exception as exc:
            logger.error(
                "Cannot read FMU model description for %s",
                str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                type(exc).__name__,
            )
            raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc

        hints: dict = {}
        for field_name, attribute_name in (
            ("description", "description"),
            ("license", "license"),
            ("author", "author"),
            ("version", "version"),
            ("generationTool", "generationTool"),
        ):
            value = normalize_xml_value(getattr(model_description, attribute_name, None))
            if value:
                hints[field_name] = value
        return hints

    return router
