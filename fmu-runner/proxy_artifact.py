"""Pure assembly helpers for reservation-scoped FMU proxy artifacts."""

from collections.abc import Iterable, Mapping
from hashlib import sha256
import hmac
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from typing import Any
from fmi_ls_struct import MANIFEST_NAME, normalize_fmi_ls_struct


RuntimeFile = tuple[Path, str]
_FMI_LS_NAMESPACE = "http://fmi-standard.org/fmi-ls-manifest"
_FMI_LS_STRUCT_MANIFEST_PATH = f"extra/{MANIFEST_NAME}/fmi-ls-manifest.xml"
_FMI_LS_STRUCT_TERMINALS_PATH = "terminalsAndIcons/terminalsAndIcons.xml"
_MAX_FMI_LS_STRUCT_XML_BYTES = 1024 * 1024


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
    names = {
        variable.get("name")
        for variable in (model_variables or ())
        if isinstance(variable.get("name"), str)
    }
    struct = normalize_fmi_ls_struct(value, variable_names=names)
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
            ET.SubElement(terminal, "TerminalMemberVariable", {
                "variableName": member["variableName"],
                "memberName": member["memberName"],
                "variableKind": member["variableKind"],
            })

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
