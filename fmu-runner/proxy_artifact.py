"""Pure assembly helpers for reservation-scoped FMU proxy artifacts."""

from collections.abc import Iterable, Mapping
import csv
from hashlib import sha256
import hmac
import io
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from typing import Any
from fmi_ls_struct import MANIFEST_NAME, normalize_fmi_ls_struct


RuntimeFile = tuple[Path, str]


class ProxyFmiLsRefSizeLimitError(ValueError):
    """Raised when generated REF resources exceed the proxy archive bound."""


_FMI_LS_NAMESPACE = "http://fmi-standard.org/fmi-ls-manifest"
_FMI_LS_STRUCT_MANIFEST_PATH = f"extra/{MANIFEST_NAME}/fmi-ls-manifest.xml"
_FMI_LS_STRUCT_TERMINALS_PATH = "terminalsAndIcons/terminalsAndIcons.xml"
_MAX_FMI_LS_STRUCT_XML_BYTES = 1024 * 1024
_FMI_LS_REF_NAME = "org.fmi-standard.fmi-ls-ref"
_FMI_LS_REF_NAMESPACE = "http://fmi-standard.org/fmi-ls-manifest"
_FMI_LS_REF_MANIFEST_PATH = f"extra/{_FMI_LS_REF_NAME}/fmi-ls-manifest.xml"
_FMI_LS_REF_VERSION = "1.0.0-alpha.1"
_SSV_NAMESPACE = "http://ssp-standard.org/SSP1/SystemStructureParameterValues"
_MA_HS_EXPERIMENTS_NAMESPACE = "http://modelica.org/HSExperiments1/HSExperiments"
_SSP_PARAMETER_SET_MEDIA_TYPE = "application/x-ssp-parameter-set"
_MA_HS_EXPERIMENTS_MEDIA_TYPE = "application/x-ma-hs-experiments"
_MAX_FMI_LS_REF_PARAMETER_FILE_BYTES = 512 * 1024
_MAX_FMI_LS_REF_STIMULI_FILE_BYTES = 1024 * 1024
_MAX_FMI_LS_REF_BUNDLE_BYTES = 64 * 1024 * 1024


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fmi_value_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".17g") if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    return None


def _ssv_parameter_type(variable: Mapping[str, Any]) -> str | None:
    type_name = str(variable.get("type") or "").strip().lower()
    return {
        "real": "Real", "float32": "Float32", "float64": "Float64",
        "integer": "Integer", "int8": "Int8", "uint8": "UInt8",
        "int16": "Int16", "uint16": "UInt16", "int32": "Int32",
        "uint32": "UInt32", "int64": "Int64", "uint64": "UInt64",
        "boolean": "Boolean", "string": "String", "enumeration": "Enumeration",
    }.get(type_name)


def _enum_name(variable: Mapping[str, Any], value: Any) -> str | None:
    enum_items = variable.get("enumItems")
    if not isinstance(enum_items, list):
        return None
    for item in enum_items:
        if not isinstance(item, dict):
            continue
        candidate = item.get("value")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and candidate == value:
            name = item.get("name")
            return name if isinstance(name, str) and name else None
    return None


def _ssv_parameter_set_bytes(
    *,
    name: str,
    parameters: Any,
    model_variables: Mapping[str, Mapping[str, Any]],
) -> bytes | None:
    if not isinstance(parameters, dict) or not parameters:
        return None

    ET.register_namespace("ssv", _SSV_NAMESPACE)
    root = ET.Element(f"{{{_SSV_NAMESPACE}}}ParameterSet", {"version": "2.0", "name": name})
    parameters_element = ET.SubElement(root, f"{{{_SSV_NAMESPACE}}}Parameters")
    for variable_name, raw_value in parameters.items():
        variable = model_variables.get(variable_name)
        if not isinstance(variable, Mapping):
            return None
        value_type = _ssv_parameter_type(variable)
        if value_type is None:
            return None
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not values or len(values) > 4096:
            return None

        rendered_values: list[str] = []
        for value in values:
            if value_type == "Enumeration":
                enum_value = _enum_name(variable, value)
                if enum_value is None:
                    return None
                rendered_values.append(enum_value)
            else:
                rendered = _fmi_value_text(value)
                if rendered is None:
                    return None
                rendered_values.append(rendered)

        parameter = ET.SubElement(parameters_element, f"{{{_SSV_NAMESPACE}}}Parameter", {"name": variable_name})
        value_attributes = {"value": " ".join(rendered_values)}
        type_element = ET.SubElement(parameter, f"{{{_SSV_NAMESPACE}}}{value_type}", value_attributes)
        if isinstance(raw_value, list):
            ET.SubElement(parameter, f"{{{_SSV_NAMESPACE}}}Dimension", {"size": str(len(raw_value))})
        # String and Enumeration arrays require one Value element per item in SSP.
        if value_type in {"String", "Enumeration"} and isinstance(raw_value, list) and len(raw_value) > 1:
            type_element.attrib.pop("value", None)
            for rendered in rendered_values:
                ET.SubElement(type_element, f"{{{_SSV_NAMESPACE}}}Value").text = rendered

    content = _xml_bytes(root)
    return content if len(content) <= _MAX_FMI_LS_REF_PARAMETER_FILE_BYTES else None


def _experiment_stimuli_bytes(input_schedule: Any) -> bytes | None:
    if not isinstance(input_schedule, list) or not input_schedule:
        return None
    first_event = input_schedule[0]
    first_values = first_event.get("values") if isinstance(first_event, dict) else None
    if not isinstance(first_values, dict) or not first_values:
        return None
    names = list(first_values)
    if any(not isinstance(name, str) or not name for name in names):
        return None

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["time", *names])
    for event in input_schedule:
        if not isinstance(event, dict) or not isinstance(event.get("values"), dict):
            return None
        values = event["values"]
        if list(values) != names:
            return None
        time_text = _fmi_value_text(event.get("time"))
        row_values = [_fmi_value_text(values.get(variable_name)) for variable_name in names]
        if time_text is None or any(value is None for value in row_values):
            return None
        writer.writerow([time_text, *row_values])
    content = output.getvalue().encode("utf-8")
    return content if len(content) <= _MAX_FMI_LS_REF_STIMULI_FILE_BYTES else None


def _fmi_ls_ref_archive_entries(
    *,
    parameter_sets: Any,
    experiments: Any,
    model_metadata: Any,
) -> tuple[tuple[str, bytes], ...]:
    """Generate reservation-safe REF resources from already-filtered metadata."""
    if not isinstance(model_metadata, Mapping):
        return ()
    raw_model_variables = model_metadata.get("modelVariables")
    if not isinstance(raw_model_variables, list):
        return ()
    model_variables = {
        variable["name"]: variable
        for variable in raw_model_variables
        if isinstance(variable, dict) and isinstance(variable.get("name"), str)
    }
    entries: list[tuple[str, bytes]] = []
    related_entries: list[tuple[str, str, str, str]] = []

    if isinstance(parameter_sets, list):
        for index, preset in enumerate(parameter_sets[:24], start=1):
            if not isinstance(preset, dict):
                continue
            preset_name = str(preset.get("name") or f"Configuration {index}")[:180]
            content = _ssv_parameter_set_bytes(
                name=preset_name,
                parameters=preset.get("parameters"),
                model_variables=model_variables,
            )
            if content is None:
                continue
            source = f"parameters/configuration-{index}.ssv"
            entries.append((f"extra/{_FMI_LS_REF_NAME}/{source}", content))
            related_entries.append((
                source,
                "parameter",
                _SSP_PARAMETER_SET_MEDIA_TYPE,
                str(preset.get("description") or "")[:1024],
            ))

    safe_experiments: list[dict[str, Any]] = []
    if isinstance(experiments, list):
        experiment_root = ET.Element(f"{{{_MA_HS_EXPERIMENTS_NAMESPACE}}}Experiments", {
            "name": "Provider experiments",
            "description": "Provider-declared experiments compatible with the authorized proxy variables.",
        })
        for index, experiment in enumerate(experiments[:128], start=1):
            if not isinstance(experiment, dict):
                continue
            parameters = experiment.get("parameters")
            options = experiment.get("options")
            schedule = experiment.get("inputSchedule") or []
            if not isinstance(parameters, dict) or not isinstance(options, dict) or not isinstance(schedule, list):
                continue

            pending_entries: list[tuple[str, bytes]] = []
            case_attributes = {"name": str(experiment.get("name") or f"Experiment {index}")[:180]}
            description = experiment.get("description")
            if isinstance(description, str) and description.strip():
                case_attributes["description"] = description[:2048]
            valid_case = True
            for option_name in ("startTime", "stopTime", "stepSize"):
                option_value = options.get(option_name)
                if option_value is None:
                    continue
                option_text = _fmi_value_text(option_value)
                if option_text is None:
                    valid_case = False
                    break
                case_attributes[option_name] = option_text

            parameter_source = None
            if valid_case and parameters:
                parameter_content = _ssv_parameter_set_bytes(
                    name=case_attributes["name"],
                    parameters=parameters,
                    model_variables=model_variables,
                )
                if parameter_content is None:
                    valid_case = False
                else:
                    parameter_source = f"parameters/experiment-{index}.ssv"
                    pending_entries.append((f"extra/{_FMI_LS_REF_NAME}/{parameter_source}", parameter_content))

            stimuli_source = None
            if valid_case and schedule:
                stimuli_content = _experiment_stimuli_bytes(schedule)
                if stimuli_content is None:
                    valid_case = False
                else:
                    stimuli_source = f"experiments/stimuli/experiment-{index}.csv"
                    pending_entries.append((f"extra/{_FMI_LS_REF_NAME}/{stimuli_source}", stimuli_content))

            if not valid_case or (
                not parameters
                and not any(option_name in case_attributes for option_name in ("startTime", "stopTime", "stepSize"))
                and not schedule
            ):
                continue

            experiment_element = ET.SubElement(
                experiment_root,
                f"{{{_MA_HS_EXPERIMENTS_NAMESPACE}}}TransientExperiment",
                case_attributes,
            )
            if parameter_source:
                ET.SubElement(experiment_element, f"{{{_MA_HS_EXPERIMENTS_NAMESPACE}}}Parameters", {
                    "source": "../" + parameter_source,
                    "type": _SSP_PARAMETER_SET_MEDIA_TYPE,
                })
            if stimuli_source:
                ET.SubElement(experiment_element, f"{{{_MA_HS_EXPERIMENTS_NAMESPACE}}}Stimuli", {
                    "source": "stimuli/" + stimuli_source.rsplit("/", 1)[-1],
                    "type": "text/csv",
                })
            entries.extend(pending_entries)
            safe_experiments.append(experiment)

        if safe_experiments:
            ET.register_namespace("", _MA_HS_EXPERIMENTS_NAMESPACE)
            exp_source = "experiments/provider-experiments.exp"
            exp_content = _xml_bytes(experiment_root)
            entries.append((f"extra/{_FMI_LS_REF_NAME}/{exp_source}", exp_content))
            related_entries.append((
                exp_source,
                "experiment/smoke-test",
                _MA_HS_EXPERIMENTS_MEDIA_TYPE,
                "Provider-declared simulation experiments.",
            ))

    if not related_entries:
        return ()

    ET.register_namespace("fmi-ls", _FMI_LS_REF_NAMESPACE)
    manifest = ET.Element("fmiReferences")
    manifest.set(f"{{{_FMI_LS_REF_NAMESPACE}}}fmi-ls-name", _FMI_LS_REF_NAME)
    manifest.set(f"{{{_FMI_LS_REF_NAMESPACE}}}fmi-ls-version", _FMI_LS_REF_VERSION)
    manifest.set(
        f"{{{_FMI_LS_REF_NAMESPACE}}}fmi-ls-description",
        "Reservation-safe parameter configurations and experiments for this proxy FMU.",
    )
    for source, role, media_type, description in related_entries:
        related = ET.SubElement(manifest, "Related", {
            "source": source,
            "role": role,
            "type": media_type,
        })
        if description:
            related.set("description", description)
    entries.append((_FMI_LS_REF_MANIFEST_PATH, _xml_bytes(manifest)))
    if sum(len(content) for _, content in entries) > _MAX_FMI_LS_REF_BUNDLE_BYTES:
        raise ProxyFmiLsRefSizeLimitError("FMI-LS-REF proxy resources exceed the archive size limit")
    return tuple(entries)


def _fmi_ls_struct_archive_entries(model_xml: bytes, value: Any) -> tuple[tuple[str, bytes], ...]:
    if value is None:
        return ()
    try:
        root = ET.fromstring(model_xml)
    except ET.ParseError:
        return ()
    if str(root.attrib.get("fmiVersion") or "").split(".", 1)[0] != "3":
        return ()
    model_variables = next(
        (child for child in root if child.tag.rsplit("}", 1)[-1] == "ModelVariables"),
        None,
    )
    names: set[str] = set()
    for variable in model_variables or ():
        name = variable.get("name")
        if isinstance(name, str):
            names.add(name)
    struct = normalize_fmi_ls_struct(value, variable_names=tuple(names))
    if not struct or not struct["maps"]:
        return ()

    ET.register_namespace("fmi-ls", _FMI_LS_NAMESPACE)
    manifest = ET.Element("fmiLayeredStandardManifest")
    manifest.set(f"{{{_FMI_LS_NAMESPACE}}}fmi-ls-name", MANIFEST_NAME)
    manifest.set(f"{{{_FMI_LS_NAMESPACE}}}fmi-ls-version", struct["manifestVersion"])

    terminals_root = ET.Element("fmiTerminalsAndIcons", {"fmiVersion": "3.0"})
    terminals = ET.SubElement(terminals_root, "Terminals")
    for map_entry in struct["maps"]:
        terminal = ET.SubElement(terminals, "Terminal", {
            "name": map_entry["name"],
            "terminalKind": map_entry["terminalKind"],
            "matchingRule": map_entry["matchingRule"],
        })
        for member in map_entry["members"]:
            terminal_member = ET.SubElement(terminal, "TerminalMemberVariable", {
                "variableName": member["variableName"],
                "memberName": member["memberName"],
                "variableKind": member["variableKind"],
            })
            ordering_constraint = member.get("orderingConstraint")
            if ordering_constraint:
                annotations = ET.SubElement(terminal_member, "Annotations")
                annotation = ET.SubElement(annotations, "Annotation", {"type": f"{MANIFEST_NAME}.orderingConstraint"})
                annotation.text = ordering_constraint

    entries = (
        (_FMI_LS_STRUCT_MANIFEST_PATH, ET.tostring(manifest, encoding="utf-8", xml_declaration=True)),
        (_FMI_LS_STRUCT_TERMINALS_PATH, ET.tostring(terminals_root, encoding="utf-8", xml_declaration=True)),
    )
    return entries if sum(len(content) for _, content in entries) <= _MAX_FMI_LS_STRUCT_XML_BYTES else ()


def build_proxy_artifact(
    *,
    model_xml: bytes,
    config_payload: Mapping[str, Any],
    runtime_files: Iterable[RuntimeFile],
    fmi_ls_struct: Any = None,
    fmi_ls_parameter_sets: Any = None,
    fmi_ls_experiments: Any = None,
    fmi_ls_model_metadata: Any = None,
) -> bytes:
    """Build the proxy archive with the established FMI runtime layout."""
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("modelDescription.xml", model_xml)
        # The native runtime receives fmuResourceLocation pointing to resources/.
        archive.writestr("resources/modelDescription.xml", model_xml)
        archive.writestr(
            "resources/config.json",
            json.dumps(config_payload, separators=(",", ":")),
        )
        for archive_name, content in _fmi_ls_struct_archive_entries(model_xml, fmi_ls_struct):
            archive.writestr(archive_name, content)
        for archive_name, content in _fmi_ls_ref_archive_entries(
            parameter_sets=fmi_ls_parameter_sets,
            experiments=fmi_ls_experiments,
            model_metadata=fmi_ls_model_metadata,
        ):
            archive.writestr(archive_name, content)
        for file_path, archive_name in runtime_files:
            archive.write(file_path, archive_name)
    return archive_buffer.getvalue()


def build_proxy_artifact_headers(
    *,
    artifact_bytes: bytes,
    lab_id: str,
    signing_key: str,
) -> dict[str, str]:
    """Build the download headers for a generated proxy artifact."""
    artifact_sha256 = sha256(artifact_bytes).hexdigest()
    headers = {
        "Content-Disposition": f'attachment; filename="fmu-proxy-lab-{lab_id}.fmu"',
        "X-Proxy-Artifact-Sha256": artifact_sha256,
    }
    if signing_key:
        signature = hmac.new(
            signing_key.encode("utf-8"),
            artifact_bytes,
            sha256,
        ).hexdigest()
        headers["X-Proxy-Artifact-Signature"] = f"hmac-sha256={signature}"
    return headers
