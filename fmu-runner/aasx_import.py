"""Parse untrusted AASX OPC packages into AAS API JSON data."""

from __future__ import annotations

import codecs
import io
import json
import logging
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Optional

from aasx_limits import (
    AasxInvalidContentError,
    AasxLimitError,
    MAX_AASX_ENVIRONMENT_PART_BYTES,
    MAX_AASX_RELATIONSHIP_PART_BYTES,
    MAX_AASX_UPLOAD_BYTES,
    validate_aasx_archive,
)

logger = logging.getLogger("fmu-runner.aasx")

_AASX_XML_SME_TYPES = {
    "annotatedRelationshipElement", "basicEventElement", "blob", "capability",
    "entity", "file", "multiLanguageProperty", "operation", "property", "range",
    "referenceElement", "relationshipElement", "submodelElementCollection",
    "submodelElementList",
}
_AASX_XML_ROOT_TYPES = {
    "assetAdministrationShell": "AssetAdministrationShell",
    "conceptDescription": "ConceptDescription",
    "submodel": "Submodel",
}
_AASX_XML_LIST_CONTAINERS = {
    "assetAdministrationShells", "category", "conceptDescriptions", "description",
    "displayName", "embeddedDataSpecifications", "extensions", "keys", "qualifiers",
    "submodelElements", "submodels", "supplementalSemanticIds",
}
_AASX_XML_LIST_VALUE_TYPES = {
    "MultiLanguageProperty",
    "SubmodelElementCollection",
    "SubmodelElementList",
}


def _aasx_xml_local_name(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].split(":")[-1]


def _parse_aasx_xml_root(xml_bytes: bytes) -> ET.Element:
    if xml_bytes.startswith((codecs.BOM_UTF32_BE, codecs.BOM_UTF32_LE)):
        security_scan_text = xml_bytes.decode("utf-32")
    elif xml_bytes.startswith((codecs.BOM_UTF16_BE, codecs.BOM_UTF16_LE)):
        security_scan_text = xml_bytes.decode("utf-16")
    elif xml_bytes.startswith(b"\x00\x00\x00<"):
        security_scan_text = xml_bytes.decode("utf-32-be")
    elif xml_bytes.startswith(b"<\x00\x00\x00"):
        security_scan_text = xml_bytes.decode("utf-32-le")
    elif xml_bytes.startswith(b"\x00<\x00?"):
        security_scan_text = xml_bytes.decode("utf-16-be")
    elif xml_bytes.startswith(b"<\x00?\x00"):
        security_scan_text = xml_bytes.decode("utf-16-le")
    else:
        # Latin-1 preserves the ASCII markup bytes used in all ASCII-compatible
        # XML encodings, including the legacy single-byte encodings AASX permits.
        security_scan_text = xml_bytes.decode("latin-1")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", security_scan_text, re.IGNORECASE):
        raise AasxInvalidContentError("AASX XML DTD and entity declarations are not supported")
    return ET.fromstring(xml_bytes)


def _aasx_xml_node_value(node: ET.Element) -> Any:
    """Convert an AAS XML object or container into its JSON API shape."""
    local_name = _aasx_xml_local_name(node.tag)
    children = list(node)
    if local_name in _AASX_XML_SME_TYPES:
        return _aasx_xml_model_element(node)
    if not children:
        text = (node.text or "").strip()
        if local_name in {"allowDuplicates", "orderRelevant"}:
            return text.lower() == "true"
        return text
    if local_name in _AASX_XML_LIST_CONTAINERS:
        return [_aasx_xml_node_value(child) for child in children]

    result: dict[str, Any] = {}
    for child in children:
        child_name = _aasx_xml_local_name(child.tag)
        child_value = _aasx_xml_node_value(child)
        if child_name in result:
            previous = result[child_name]
            result[child_name] = (
                [*previous, child_value]
                if isinstance(previous, list)
                else [previous, child_value]
            )
        else:
            result[child_name] = child_value
    return result


def _aasx_xml_model_element(node: ET.Element) -> dict[str, Any]:
    element_type = _aasx_xml_local_name(node.tag)
    model_type = element_type[0].upper() + element_type[1:]
    result: dict[str, Any] = {"modelType": model_type}
    for child in list(node):
        field_name = _aasx_xml_local_name(child.tag)
        if model_type == "Blob" and field_name == "value" and not list(child):
            # AAS XML serializers may line-wrap base64 Blob payloads as text.
            value = re.sub(r"\s+", "", child.text or "")
        elif field_name == "value" and list(child):
            value_children = list(child)
            if model_type in _AASX_XML_LIST_VALUE_TYPES or all(
                _aasx_xml_local_name(item.tag) in _AASX_XML_SME_TYPES for item in value_children
            ):
                value = [_aasx_xml_node_value(item) for item in value_children]
            elif all(
                _aasx_xml_local_name(item.tag).startswith("langString")
                for item in value_children
            ):
                value = [_aasx_xml_node_value(item) for item in value_children]
            else:
                value = _aasx_xml_node_value(child)
        else:
            value = _aasx_xml_node_value(child)
        if field_name in result:
            previous = result[field_name]
            result[field_name] = (
                [*previous, value]
                if isinstance(previous, list)
                else [previous, value]
            )
        else:
            result[field_name] = value
    return result


def _parse_aasx_xml_environment(xml_bytes: bytes) -> Optional[dict]:
    try:
        root = _parse_aasx_xml_root(xml_bytes)
    except ET.ParseError:
        return None
    if _aasx_xml_local_name(root.tag) != "environment":
        return None

    environment: dict[str, list] = {
        "assetAdministrationShells": [],
        "submodels": [],
        "conceptDescriptions": [],
    }
    for child in list(root):
        field_name = _aasx_xml_local_name(child.tag)
        if field_name not in environment:
            continue
        objects = []
        for item in list(child):
            object_type = _aasx_xml_local_name(item.tag)
            parsed = _aasx_xml_node_value(item)
            if object_type in _AASX_XML_ROOT_TYPES and isinstance(parsed, dict):
                parsed["modelType"] = _AASX_XML_ROOT_TYPES[object_type]
            objects.append(parsed)
        environment[field_name] = objects
    return environment


def parse_aasx(
    aasx_bytes: bytes,
    *,
    max_upload_bytes: int = MAX_AASX_UPLOAD_BYTES,
    environment_part_bytes: int = MAX_AASX_ENVIRONMENT_PART_BYTES,
    relationship_part_bytes: int = MAX_AASX_RELATIONSHIP_PART_BYTES,
) -> dict:
    """
    Parse an AASX package (ZIP/OPC container) and extract the AAS environment.

    AASX is a ZIP archive with a ``_rels/.rels`` relationship file pointing to
    the AAS origin part (typically a JSON or XML file).  Returns a dict with
    ``shells``, ``submodels``, and ``conceptDescriptions`` lists.
    """
    shells: list = []
    submodels: list = []
    concept_descs: list = []

    if len(aasx_bytes) > max_upload_bytes:
        raise AasxLimitError("AASX upload exceeds the 50 MiB limit")

    try:
        with zipfile.ZipFile(io.BytesIO(aasx_bytes)) as zf:
            infos = validate_aasx_archive(zf.infolist(), len(aasx_bytes))
            info_by_name = {info.filename: info for info in infos}
            names = set(info_by_name)

            def read_part(name: str, max_bytes: int) -> bytes:
                info = info_by_name[name]
                if info.file_size > max_bytes:
                    raise AasxLimitError(f"AASX part {name} exceeds its {max_bytes} byte limit")
                return zf.read(info)

            # Step 1: follow _rels/.rels to find the AAS origin part
            origin_path: Optional[str] = None
            origin_part_path: Optional[str] = None
            rels_path = "_rels/.rels"
            if rels_path in names:
                try:
                    root = _parse_aasx_xml_root(
                        read_part(rels_path, relationship_part_bytes)
                    )
                    ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
                    for rel in root.findall("r:Relationship", ns):
                        rel_type = rel.get("Type", "")
                        target = rel.get("Target", "").lstrip("/")
                        if "aasx-origin" in rel_type and target in names:
                            origin_part_path = target
                        elif "aas-spec" in rel_type and target in names:
                            origin_path = target

                    if origin_part_path:
                        origin_rels_path = posixpath.join(
                            posixpath.dirname(origin_part_path),
                            "_rels",
                            f"{posixpath.basename(origin_part_path)}.rels",
                        )
                        if origin_rels_path in names:
                            origin_root = _parse_aasx_xml_root(read_part(
                                origin_rels_path,
                                relationship_part_bytes,
                            ))
                            for rel in origin_root.findall("r:Relationship", ns):
                                if "aas-spec" not in rel.get("Type", ""):
                                    continue
                                target = rel.get("Target", "")
                                spec_path = posixpath.normpath(posixpath.join(
                                    posixpath.dirname(origin_part_path),
                                    target.lstrip("/"),
                                ))
                                if spec_path in names:
                                    origin_path = spec_path
                                    break
                except ET.ParseError:
                    # A malformed relationships part can be handled by JSON fallback scanning.
                    pass

            # Step 2: candidates: origin part first, then JSON scan fallback.
            candidates: list = []
            if origin_path:
                candidates.append(origin_path)
            candidates.extend(sorted(
                name for name in names
                if name != origin_path
                and name.lower().endswith((".json", ".xml"))
                and not name.startswith("[")
            ))

            for candidate in candidates:
                if not candidate or candidate not in names:
                    continue
                try:
                    content = read_part(candidate, environment_part_bytes)
                    if candidate.lower().endswith(".xml"):
                        data = _parse_aasx_xml_environment(content)
                        if data is None:
                            continue
                    else:
                        data = json.loads(content)
                    if "assetAdministrationShells" in data or "submodels" in data:
                        shells = data.get("assetAdministrationShells", [])
                        submodels = data.get("submodels", [])
                        concept_descs = data.get("conceptDescriptions", [])
                        break
                except (json.JSONDecodeError, KeyError, RecursionError, UnicodeDecodeError):
                    continue
    except zipfile.BadZipFile:
        logger.error("AASX upload: not a valid ZIP/AASX file")

    return {"shells": shells, "submodels": submodels, "conceptDescriptions": concept_descs}
