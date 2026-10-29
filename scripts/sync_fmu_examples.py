"""Sync canonical FMU examples into Gateway's ignored development data directory.

The six reference FMUs and Smart Warehouse are synced by default. Local
BOPTEST, qFMU, water-tank, DC-motor, inverted-pendulum and lateral-motion demos
require explicit flags. This script never adds demo files to Gateway images or
release packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import shutil
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


GATEWAY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES_ROOT = GATEWAY_ROOT.parent / "FMU-Executor" / "examples"
REFERENCE_FMU_NAMES = {
    "BinaryClockTest.fmu",
    "BouncingBall.fmu",
    "Feedthrough.fmu",
    "Stair.fmu",
    "StateSpace.fmu",
    "VanDerPol.fmu",
}
STATIC_IMPORT_PATTERNS = (
    re.compile(r"(?m)^\s*import\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"(?m)^\s*import\s+(?!['\"])[\s\S]*?\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"(?m)^\s*export\s+[\s\S]*?\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
)
CSS_URL_PATTERN = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
BOPTEST_COMPLEX_FMU_NAME = "BOPTEST-MultizoneOfficeComplexAir.fmu"
BOPTEST_COMPLEX_APP_NAME = "BOPTEST-MultizoneOfficeComplexAir.webapp.zip"
BOPTEST_COMPLEX_LICENSE_NAME = "BOPTEST-ComplexAir.LICENSE.txt"
BOPTEST_COMPLEX_ZONES = ("Cor", "Sou", "Eas", "Nor", "Wes")
QFMU_LICENSE_NAME = "LICENSE-qFMU.txt"
QFMU_MODELS = {
    "qFMU_FirstOrder.fmu": ({"u1"}, {"y1"}),
    "qFMU_SecondOrder.fmu": ({"u1"}, {"y1"}),
    "qFMU_SISO.fmu": ({"u1"}, {"y1"}),
    "qFMU_MIMO.fmu": ({"u1", "u2"}, {"y1", "y2"}),
}
QFMU_WEBAPP_REQUIRED_FILES = {
    "index.html",
    "app.js",
    "styles.css",
    "app-config.json",
    "models.json",
    "qfmuModelUtils.js",
    "components/QfmuResponseChart.js",
}
FMU_SESSION_APP_MARKERS = (
    "decentralabs:digital-twin-connect",
    "decentralabs:fmu-connection-request",
    "decentralabs:fmu-connection-ready",
)
DC_MOTOR_FMU_NAME = "DC_motor.fmu"
DC_MOTOR_APP_NAME = "DC_motor.webapp.zip"
INVERTED_PENDULUM_FMU_NAME = "InvertedPendulum.fmu"
INVERTED_PENDULUM_APP_NAME = "InvertedPendulum.webapp.zip"
LATERAL_MOTION_FMU_NAME = "LateralMotionControl.fmu"
LATERAL_MOTION_APP_NAME = "LateralMotionControl.webapp.zip"
WATER_TANK_FMU_NAME = "singlewatertank-20sim.fmu"
WATER_TANK_APP_NAME = "singlewatertank-20sim.webapp.zip"
DC_MOTOR_REQUIRED_PARAMETERS = {
    "sine.offset",
    "speedController.k",
    "speedController.Ti",
    "damper.d",
    "spring.k",
    "torqueStep.stepTorque",
    "torqueStep.startTime",
    "torqueStep.offsetTorque",
    "data.Ja.value",
    "data.Jm.value",
}
DC_MOTOR_REQUIRED_OUTPUT_UNITS = {
    "out_control_err": "rad/s",
    "out_load_speed": "rad/s",
    "out_motor_speed": "rad/s",
    "out_motor_position": "rad",
    "out_gear_position": "rad",
    "out_load_position": "rad",
    "out_shaft_twist": "rad",
    "out_reference": "rad/s",
    "out_motor_torque": "N.m",
    "out_load_torque": "N.m",
    "out_shaft_torque_on_load": "N.m",
}
EXTERNAL_ANCHOR_HREF_PATTERN = re.compile(
    r'(<a\b[^>]*?\bhref\s*=\s*)(["\'])https?://[^"\']*\2',
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_linux_x64_fmu(path: Path) -> set[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"Invalid FMU archive {path}: {error}") from error

    if "modelDescription.xml" not in names:
        raise ValueError(f"FMU has no modelDescription.xml: {path}")

    linux_x64_entries = {
        name for name in names
        if name.startswith(("binaries/linux64/", "binaries/x86_64-linux/"))
        and not name.endswith("/")
    }
    if not linux_x64_entries:
        raise ValueError(f"FMU has no Linux x86_64 binary: {path}")
    return names


def validate_local_glb_output_bindings(
    scene_path: Path,
    fmu_path: Path,
    *,
    require_bindings: bool = True,
    required_bindings: set[tuple[str, str]] | None = None,
) -> None:
    """Check companion GLB bindings against the FMU interface they visualize."""
    try:
        scene_bytes = scene_path.read_bytes()
        if len(scene_bytes) < 20 or scene_bytes[:4] != b"glTF":
            raise ValueError("invalid GLB header")
        version, declared_length = struct.unpack_from("<II", scene_bytes, 4)
        chunk_length, chunk_type = struct.unpack_from("<I4s", scene_bytes, 12)
        if version != 2 or declared_length != len(scene_bytes) or chunk_type != b"JSON":
            raise ValueError("invalid GLB version, length, or JSON chunk")
        document = json.loads(scene_bytes[20 : 20 + chunk_length].decode("utf-8").rstrip("\x00 "))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, struct.error, ValueError) as error:
        raise ValueError(f"Invalid companion GLB {scene_path}: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("nodes"), list):
        raise ValueError(f"Invalid companion GLB {scene_path}: the node list is missing")

    try:
        with zipfile.ZipFile(fmu_path) as archive:
            model_description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Unable to inspect FMU variables in {fmu_path}: {error}") from error

    model_variables = model_description.find("ModelVariables")
    if model_variables is None:
        raise ValueError(f"FMU has no ModelVariables interface: {fmu_path}")
    variables = {
        variable.get("name"): variable
        for variable in model_variables
        if isinstance(variable.get("name"), str)
    }
    targets = {
        "position.x", "position.y", "position.z",
        "rotation.x", "rotation.y", "rotation.z",
        "scale.x", "scale.y", "scale.z", "visible", "material.color",
    }
    bindings_found = 0
    binding_pairs: set[tuple[str, str]] = set()
    for node_index, node in enumerate(document.get("nodes", [])):
        extras = node.get("extras") if isinstance(node, dict) else None
        if not isinstance(extras, dict) or "fmiBindings" not in extras:
            continue
        bindings = extras["fmiBindings"]
        if not isinstance(bindings, list):
            raise ValueError(f"{scene_path}: node {node_index} fmiBindings must be an array")
        for binding_index, binding in enumerate(bindings):
            bindings_found += 1
            if not isinstance(binding, dict):
                raise ValueError(f"{scene_path}: node {node_index} binding {binding_index} must be an object")
            name = binding.get("variable")
            if not isinstance(name, str):
                raise ValueError(f"{scene_path}: node {node_index} binding {binding_index} must name an FMU variable")
            variable = variables.get(name)
            if variable is None:
                raise ValueError(f"{scene_path}: binding references unknown FMU variable {name!r}")
            if (variable.get("causality") or "local").lower() != "output":
                raise ValueError(
                    f"{scene_path}: {name!r} is not an FMU output; local GLB companions use output bindings, "
                    "while writable inputs remain in Run Controls"
                )
            target = binding.get("target")
            if not isinstance(target, str) or target not in targets:
                raise ValueError(f"{scene_path}: {name!r} has an unsupported target {target!r}")
            binding_pairs.add((name, target))
            for field in ("scale", "offset", "visibleWhenGreaterThanOrEqual"):
                if field in binding and (
                    isinstance(binding[field], bool)
                    or not isinstance(binding[field], (int, float))
                    or not math.isfinite(binding[field])
                ):
                    raise ValueError(f"{scene_path}: {name!r} has an invalid {field}")

    if bindings_found == 0 and require_bindings:
        raise ValueError(f"The local GLB has no FMI output bindings: {scene_path}")
    missing_bindings = (required_bindings or set()) - binding_pairs
    if missing_bindings:
        missing = ", ".join(f"{name} -> {target}" for name, target in sorted(missing_bindings))
        raise ValueError(f"{scene_path}: required FMI output bindings are missing: {missing}")


def copy_verified(origin: Path, destination: Path) -> None:
    if not origin.is_file():
        raise FileNotFoundError(f"Canonical example asset not found: {origin}")
    shutil.copy2(origin, destination)
    if sha256(origin) != sha256(destination):
        raise OSError(f"Copy verification failed for {destination}")
    print(f"Synced {origin.name} -> {destination}")


class _WebAppAssetParser(HTMLParser):
    """Collect runtime assets referenced directly from static HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for name in ("src", "poster", "data"):
            reference = attributes.get(name)
            if reference:
                self.references.append(reference)

        href = attributes.get("href")
        if tag == "link" and href:
            relationships = set((attributes.get("rel") or "").lower().split())
            if relationships & {"stylesheet", "icon", "modulepreload", "preload", "manifest"}:
                self.references.append(href)


def _resolve_webapp_asset_reference(source: str, reference: str, files: set[str]) -> str | None:
    if reference.startswith(("data:", "blob:", "#")):
        return None
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or reference.startswith("/"):
        raise ValueError(f"Web app has an external or root-relative runtime asset: {source}: {reference}")
    if not parsed.path or "\\" in parsed.path:
        raise ValueError(f"Web app has an invalid runtime asset path: {source}: {reference}")

    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), parsed.path))
    if target in {".", ".."} or target.startswith("../") or target not in files:
        raise ValueError(f"Web app asset is missing from the bundle: {source}: {reference}")
    return target


def validate_webapp_bundle(path: Path) -> set[str]:
    """Check that a static web app archive contains its full local asset graph."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            files = {name for name in names if not name.endswith("/")}
            if len(files) != sum(not name.endswith("/") for name in names):
                raise ValueError(f"The web app archive contains duplicate file paths: {path}")
            if "index.html" not in files:
                raise ValueError(f"The web app archive has no root index.html: {path}")

            for name in sorted(files):
                pure_path = PurePosixPath(name)
                if (
                    "\\" in name
                    or pure_path.is_absolute()
                    or any(part in {".", ".."} for part in pure_path.parts)
                ):
                    raise ValueError(f"The web app archive contains an unsafe path: {name}")

            for name in sorted(files):
                suffix = PurePosixPath(name).suffix.lower()
                if suffix in {".js", ".mjs"}:
                    source = archive.read(name).decode("utf-8")
                    references = {
                        match.group(1)
                        for pattern in STATIC_IMPORT_PATTERNS
                        for match in pattern.finditer(source)
                    }
                elif suffix == ".html":
                    source = archive.read(name).decode("utf-8")
                    parser = _WebAppAssetParser()
                    parser.feed(source)
                    references = set(parser.references)
                    references.update(match.group(2).strip() for match in CSS_URL_PATTERN.finditer(source))
                elif suffix == ".css":
                    source = archive.read(name).decode("utf-8")
                    references = {match.group(2).strip() for match in CSS_URL_PATTERN.finditer(source)}
                    references.update(match.group(1) for match in re.finditer(
                        r"@import\s+(?:url\(\s*)?['\"]?([^'\"\s)]+)", source, re.IGNORECASE,
                    ))
                else:
                    continue

                for reference in sorted(references):
                    if suffix in {".js", ".mjs"} and not reference.startswith(("./", "../")):
                        raise ValueError(f"Web app has an unbundled module import: {name}: {reference}")
                    _resolve_webapp_asset_reference(name, reference, files)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid static web app bundle {path}: {error}") from error

    return files


def validate_fmu_session_app(path: Path) -> None:
    """Require companion apps to use the host grant and generic FMI session protocol."""
    try:
        with zipfile.ZipFile(path) as archive:
            sources = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if PurePosixPath(name).suffix.lower() in {".js", ".mjs"}
            )
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid companion app source in {path}: {error}") from error

    missing_markers = [marker for marker in FMU_SESSION_APP_MARKERS if marker not in sources]
    if missing_markers:
        raise ValueError(
            f"The companion app does not implement the generic FMU session handshake: {path}"
        )
    if "/api/dev/" in sources or "simulations/stream" in sources:
        raise ValueError(
            f"The companion app must run the FMU through the generic Gateway session, not a demo endpoint: {path}"
        )


def validate_qfmu_fmu(path: Path, expected_inputs: set[str], expected_outputs: set[str]) -> None:
    names = validate_linux_x64_fmu(path)
    identifier = path.stem
    expected_binary = f"binaries/linux64/{identifier}.so"
    if expected_binary not in names:
        raise ValueError(f"qFMU is missing its Linux binary {expected_binary}: {path}")

    try:
        with zipfile.ZipFile(path) as archive:
            description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Invalid qFMU model description {path}: {error}") from error

    if description.attrib.get("fmiVersion") != "2.0":
        raise ValueError(f"qFMU must use FMI 2.0: {path}")
    if description.attrib.get("generationTool") != "qfmu":
        raise ValueError(f"The FMU was not generated by qFMU: {path}")
    co_simulation = description.find("{*}CoSimulation")
    if co_simulation is None or description.find("{*}ModelExchange") is None:
        raise ValueError(f"qFMU must expose both FMI Co-Simulation and Model Exchange: {path}")
    if co_simulation.attrib.get("modelIdentifier") != path.stem:
        raise ValueError(f"The qFMU modelIdentifier must match its FMI binary filename: {path}")

    variables = description.find("{*}ModelVariables")
    if variables is None:
        raise ValueError(f"qFMU has no model variables: {path}")
    inputs: set[str] = set()
    outputs: set[str] = set()
    for variable in variables:
        causality = variable.attrib.get("causality")
        if causality not in {"input", "output"}:
            continue

        name = variable.attrib.get("name")
        if not name:
            raise ValueError(f"qFMU has an unnamed {causality} variable: {path}")

        if causality == "input":
            inputs.add(name)
        else:
            outputs.add(name)
    if inputs != expected_inputs or outputs != expected_outputs:
        raise ValueError(
            f"Unexpected qFMU variables in {path.name}: inputs={sorted(inputs)}, "
            f"outputs={sorted(outputs)}"
        )


def validate_qfmu_webapp(path: Path) -> None:
    validate_webapp_bundle(path)
    validate_fmu_session_app(path)
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = QFMU_WEBAPP_REQUIRED_FILES - names
            if missing:
                raise ValueError(f"qFMU app is missing files: {', '.join(sorted(missing))}")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise ValueError(f"Invalid qFMU companion app {path}: {error}") from error


def validate_dc_motor_fmu(path: Path) -> None:
    names = validate_linux_x64_fmu(path)
    expected_binary = "binaries/linux64/DC_motor_with_positions.so"
    if expected_binary not in names:
        raise ValueError(f"The DC motor FMU is missing its Linux x86_64 binary {expected_binary}.")
    try:
        with zipfile.ZipFile(path) as archive:
            description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Invalid DC motor model description: {error}") from error

    if description.attrib.get("fmiVersion") != "2.0" or description.attrib.get("modelName") != "DC_motor_with_positions":
        raise ValueError("The local DC motor demo requires the reviewed FMI 2.0 DC_motor_with_positions wrapper.")
    co_simulation = description.find("{*}CoSimulation")
    if co_simulation is None or co_simulation.attrib.get("modelIdentifier") != "DC_motor_with_positions":
        raise ValueError("The reviewed DC motor FMU must expose Co-Simulation as DC_motor_with_positions.")
    variables = description.find("{*}ModelVariables")
    if variables is None:
        raise ValueError("The DC motor FMU has no model variables.")

    inputs: set[str] = set()
    outputs: set[str] = set()
    parameters: set[str] = set()
    for variable in variables:
        name = variable.attrib.get("name")
        causality = variable.attrib.get("causality")
        if not name:
            continue
        if causality == "input":
            inputs.add(name)
        elif causality == "output":
            outputs.add(name)
        elif causality == "parameter" and variable.attrib.get("variability") != "constant":
            parameters.add(name)
    if inputs != {"in_torque"}:
        raise ValueError(f"Unexpected DC motor FMU inputs: {sorted(inputs)}")
    missing_outputs = set(DC_MOTOR_REQUIRED_OUTPUT_UNITS) - outputs
    if missing_outputs:
        raise ValueError("The DC motor FMU is missing output signals: " + ", ".join(sorted(missing_outputs)))
    for variable in variables:
        variable_name = variable.attrib.get("name")
        if variable_name is None or variable_name not in DC_MOTOR_REQUIRED_OUTPUT_UNITS:
            continue
        expected_unit = DC_MOTOR_REQUIRED_OUTPUT_UNITS[variable_name]
        real = variable.find("{*}Real")
        if variable.attrib.get("causality") != "output" or real is None or real.attrib.get("unit") != expected_unit:
            raise ValueError(f"The DC motor output {variable_name} must be FMI Real with unit {expected_unit}.")
    missing_parameters = DC_MOTOR_REQUIRED_PARAMETERS - parameters
    if missing_parameters:
        raise ValueError("The DC motor FMU is missing tunable parameters: " + ", ".join(sorted(missing_parameters)))


def validate_inverted_pendulum_fmu(path: Path) -> None:
    names = validate_linux_x64_fmu(path)
    if "binaries/linux64/InvertedPendulum.so" not in names:
        raise ValueError("The inverted-pendulum FMU is missing its Linux x86_64 model binary.")
    try:
        with zipfile.ZipFile(path) as archive:
            description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Invalid inverted-pendulum model description: {error}") from error

    if description.attrib.get("fmiVersion") != "2.0":
        raise ValueError("The inverted-pendulum FMU must use FMI 2.0.")
    co_simulation = description.find("{*}CoSimulation")
    if co_simulation is None or co_simulation.attrib.get("modelIdentifier") != "InvertedPendulum":
        raise ValueError("The inverted-pendulum FMU must expose FMI Co-Simulation as InvertedPendulum.")
    variables = description.find("{*}ModelVariables")
    if variables is None:
        raise ValueError("The inverted-pendulum FMU has no model variables.")

    interface: dict[str, set[str]] = {"input": set(), "output": set(), "parameter": set()}
    for variable in variables:
        name = variable.attrib.get("name")
        causality = variable.attrib.get("causality")
        if name and causality in interface:
            interface[causality].add(name)
    if "inputForce" not in interface["input"]:
        raise ValueError("The inverted-pendulum FMU is missing inputForce.")
    if not {"displacement", "velocity", "angle", "angularvelocity"} <= interface["output"]:
        raise ValueError("The inverted-pendulum FMU is missing cart-pole state outputs.")
    if not {"phi_start", "disp_start", "velo_start", "w_start"} <= interface["parameter"]:
        raise ValueError("The inverted-pendulum FMU is missing its initial-state parameters.")


def validate_dc_motor_app(path: Path) -> None:
    validate_webapp_bundle(path)
    validate_fmu_session_app(path)
    try:
        with zipfile.ZipFile(path) as archive:
            files = set(archive.namelist())
            required = {
                "index.html",
                "app.js",
                "model.js",
                "scene.js",
                "styles.css",
                "vendor/three.module.js",
                "vendor/three.core.js",
                "vendor/OrbitControls.js",
                "vendor/THREE-LICENSE.txt",
            }
            missing = required - files
            if missing:
                raise ValueError("The DC motor web app is incomplete: " + ", ".join(sorted(missing)))
            app = archive.read("app.js").decode("utf-8")
            index = archive.read("index.html").decode("utf-8")
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid DC motor app bundle: {error}") from error
    index_without_source_links = EXTERNAL_ANCHOR_HREF_PATTERN.sub(r"\1\2\2", index)
    if any(re.search(r"https?://", source, re.IGNORECASE) for source in (index_without_source_links, app)):
        raise ValueError("The DC motor app must not depend on external runtime services.")


def validate_water_tank_app(path: Path) -> None:
    validate_webapp_bundle(path)
    validate_fmu_session_app(path)
    required_files = {
        "index.html",
        "app.js",
        "scene.js",
        "styles.css",
        "vendor/three.module.js",
        "vendor/three.core.js",
        "vendor/OrbitControls.js",
        "vendor/THREE-LICENSE.txt",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            files = set(archive.namelist())
            missing = required_files - files
            if missing:
                raise ValueError("The water-tank web app is incomplete: " + ", ".join(sorted(missing)))
            app = archive.read("app.js").decode("utf-8")
            index = archive.read("index.html").decode("utf-8")
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid water-tank app bundle: {error}") from error
    if any("http://" in source or "https://" in source for source in (app, index)):
        raise ValueError("The water-tank app must not depend on external runtime services.")


def validate_local_fmu_session_app(path: Path, demo_name: str, required_assets: set[str] | None = None) -> None:
    files = validate_webapp_bundle(path)
    validate_fmu_session_app(path)
    missing = (required_assets or set()) - files
    if missing:
        raise ValueError(f"The local {demo_name} app is missing: " + ", ".join(sorted(missing)))


def validate_boptest_complex_air_fmu(path: Path) -> set[str]:
    names = validate_linux_x64_fmu(path)
    required_binaries = {"binaries/linux64/wrapped.so"}
    missing_binaries = required_binaries - names
    if missing_binaries:
        raise ValueError(
            "BOPTEST Complex Air FMU is missing its Linux x86_64 runtime libraries: "
            + ", ".join(sorted(missing_binaries))
        )

    try:
        with zipfile.ZipFile(path) as archive:
            description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Invalid BOPTEST Complex Air FMU model description: {error}") from error

    if description.attrib.get("fmiVersion") != "2.0":
        raise ValueError("BOPTEST Complex Air FMU must use FMI 2.0.")
    if description.find("{*}CoSimulation") is None:
        raise ValueError("BOPTEST Complex Air FMU must expose FMI Co-Simulation.")

    variables = description.find("{*}ModelVariables")
    if variables is None:
        raise ValueError("BOPTEST Complex Air FMU has no model variables.")
    outputs = {
        element.attrib.get("name")
        for element in variables
        if element.attrib.get("causality") == "output"
    }
    required_outputs = {
        f"floor{floor}_reaZon{zone}_{signal}"
        for floor in range(1, 4)
        for zone in BOPTEST_COMPLEX_ZONES
        for signal in ("TZon_y", "CO2Zon_y", "V_flow_y", "yDam_y", "yReheaVal_y")
    } | {
        f"floor{floor}_reaAHU_PFan{side}_y"
        for floor in range(1, 4)
        for side in ("Sup", "Ret")
    } | {
        "reaHotWatSys_reaPBoi_y",
        "reaChiWatSys_reaPChi_y",
        "reaChiWatSys_reaPCooTow_y",
        "weaSta_reaWeaTDryBul_y",
        "weaSta_reaWeaHGloHor_y",
        "weaSta_reaWeaSolAlt_y",
        "weaSta_reaWeaSolHouAng_y",
    }
    missing_outputs = required_outputs - outputs
    if missing_outputs:
        raise ValueError(
            "BOPTEST Complex Air FMU is missing required scene signals: "
            + ", ".join(sorted(missing_outputs))
        )

    inputs = {
        element.attrib.get("name")
        for element in variables
        if element.attrib.get("causality") == "input"
    }
    required_inputs = {
        f"floor{floor}_oveZon{zone}_TZon{kind}_{suffix}"
        for floor in range(1, 4)
        for zone in BOPTEST_COMPLEX_ZONES
        for kind in ("HeaSet", "CooSet")
        for suffix in ("u", "activate")
    }
    missing_inputs = required_inputs - inputs
    if missing_inputs:
        raise ValueError(
            "BOPTEST Complex Air FMU is missing zone setpoint inputs: "
            + ", ".join(sorted(missing_inputs))
        )

    required_resources = {
        "resources/wholebuilding96_spawn.idf",
        "resources/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
        "resources/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.mos",
        "resources/weather.csv",
        "resources/internal_setpoints_occupancy.csv",
        "resources/prices.csv",
        "resources/emissions.csv",
    }
    missing_resources = required_resources - names
    if missing_resources:
        raise ValueError(
            "BOPTEST Complex Air FMU is missing its self-contained resources: "
            + ", ".join(sorted(missing_resources))
        )
    return names


def sync(
    examples_root: Path,
    target: Path,
    *,
    include_local_boptest: bool = False,
    include_local_qfmu: bool = False,
    include_local_dc_motor: bool = False,
    include_local_water_tank: bool = False,
    include_local_inverted_pendulum: bool = False,
    include_local_lateral_motion: bool = False,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    boptest_target = target / "local-demos" / "boptest-building" / "linux64"
    legacy_boptest_root = target / "local-demos" / "boptest-building-complex"
    # Remove stale local copies of retired examples from existing workspaces.
    for obsolete_name in (
        "SmartFactoryCell.fmu",
        "SmartFactoryCell.glb",
        "SmartFactoryCell.LICENSE.txt",
        "Dahlquist.fmu",
        "BOPTEST-MultizoneOfficeComplexAir.fmu",
        "BOPTEST-MultizoneOfficeComplexAir.webapp.zip",
        "BOPTEST-MultizoneOfficeComplexAir.LICENSE.txt",
        "BOPTEST-ComplexAir.LICENSE.txt",
        "BOPTEST-MultizoneOfficeSimpleHydronic.fmu",
        "BOPTEST-MultizoneOfficeSimpleHydronic.webapp.zip",
        "BOPTEST-MultizoneOfficeSimpleHydronic.LICENSE.txt",
        "BOPTEST.LICENSE.txt",
        "BOPTEST-MultizoneOfficeSimpleAir.fmu",
        "BOPTEST-SimpleAir-TestPatch.fmu",
        "BOPTEST-SimpleAir-TestPatch2.fmu",
    ):
        (target / obsolete_name).unlink(missing_ok=True)
    if include_local_boptest and boptest_target.is_dir():
        for local_boptest_name in (
            BOPTEST_COMPLEX_FMU_NAME,
            BOPTEST_COMPLEX_APP_NAME,
            "BOPTEST-MultizoneOfficeComplexAir.LICENSE.txt",
        ):
            (boptest_target / local_boptest_name).unlink(missing_ok=True)
    if legacy_boptest_root.exists():
        resolved_legacy_root = legacy_boptest_root.resolve()
        resolved_local_demos = (target / "local-demos").resolve()
        if legacy_boptest_root.is_symlink() or resolved_legacy_root.parent != resolved_local_demos:
            raise ValueError(f"Refusing to remove unexpected legacy BOPTEST path: {legacy_boptest_root}")
        shutil.rmtree(legacy_boptest_root)
    reference_root = examples_root / "reference-fmus"
    canonical_reference_fmus = {
        path.name: path for path in reference_root.glob("*.fmu") if path.is_file()
    }
    missing = REFERENCE_FMU_NAMES - canonical_reference_fmus.keys()
    if missing:
        raise FileNotFoundError(
            "Canonical reference FMUs are missing: " + ", ".join(sorted(missing))
        )

    for name in sorted(REFERENCE_FMU_NAMES):
        source = canonical_reference_fmus[name]
        names = validate_linux_x64_fmu(source)
        if name == "BinaryClockTest.fmu":
            required = {
                "binaries/x86_64-linux/BinaryClockTest.so",
                "binaries/x86_64-windows/BinaryClockTest.dll",
            }
            missing_platforms = required - names
            if missing_platforms:
                raise ValueError(
                    "BinaryClockTest must contain both Windows and Linux x86_64 builds; "
                    f"missing: {', '.join(sorted(missing_platforms))}"
                )
        copy_verified(source, target / name)

    copy_verified(reference_root / "LICENSE.txt", target / "Reference-FMUs.LICENSE.txt")

    smart_warehouse_root = examples_root / "smart-warehouse-cell"
    warehouse_fmu = smart_warehouse_root / "SmartWarehouseCell-linux64.fmu"
    warehouse_scene = smart_warehouse_root / "smart-warehouse-cell.glb"
    warehouse_app = smart_warehouse_root / "SmartWarehouseCell.webapp.zip"
    warehouse_license = smart_warehouse_root / "LICENSE.txt"
    warehouse_entries = validate_linux_x64_fmu(warehouse_fmu)
    if "resources/smart-warehouse-cell.glb" not in warehouse_entries:
        raise ValueError("The Smart Warehouse FMU is missing its embedded GLB scene.")
    with zipfile.ZipFile(warehouse_fmu) as archive:
        warehouse_embedded_scene = archive.read("resources/smart-warehouse-cell.glb")
    if warehouse_embedded_scene != warehouse_scene.read_bytes():
        raise ValueError("The Smart Warehouse FMU's embedded scene differs from its companion GLB.")
    validate_local_glb_output_bindings(warehouse_scene, warehouse_fmu)
    validate_webapp_bundle(warehouse_app)
    with zipfile.ZipFile(warehouse_app) as archive:
        app_names = set(archive.namelist())
        if not {"index.html", "app.js", "scene.js"}.issubset(app_names):
            raise ValueError("The Smart Warehouse app bundle is missing its procedural scene modules.")
        if "warehouse.glb" in app_names or "vendor/GLTFLoader.js" in app_names:
            raise ValueError("The Smart Warehouse Three.js app must build its scene independently from the GLB.")
        app_script = archive.read("app.js").decode("utf-8")
        if "createSmartWarehouseScene" not in app_script or "scene.js" not in app_script:
            raise ValueError("The Smart Warehouse app bundle does not load its procedural scene module.")
        if "playbackControlPosition" not in app_script or "bottom-right" not in app_script:
            raise ValueError("The Smart Warehouse app must request the bottom-right playback control position.")

    copy_verified(warehouse_fmu, target / "SmartWarehouseCell.fmu")
    copy_verified(warehouse_scene, target / "SmartWarehouseCell.glb")
    copy_verified(warehouse_app, target / "SmartWarehouseCell.webapp.zip")
    copy_verified(warehouse_license, target / "SmartWarehouseCell.LICENSE.txt")

    if include_local_inverted_pendulum:
        pendulum_root = examples_root / "local-demos" / "inverted-pendulum"
        pendulum_fmu = pendulum_root / INVERTED_PENDULUM_FMU_NAME
        pendulum_app = pendulum_root / INVERTED_PENDULUM_APP_NAME
        pendulum_scene = pendulum_root / "InvertedPendulum.glb"
        validate_inverted_pendulum_fmu(pendulum_fmu)
        validate_local_glb_output_bindings(pendulum_scene, pendulum_fmu)
        validate_local_fmu_session_app(pendulum_app, "inverted-pendulum")
        pendulum_target = target / "local-demos" / "inverted-pendulum" / "linux64"
        pendulum_target.mkdir(parents=True, exist_ok=True)
        copy_verified(pendulum_fmu, pendulum_target / INVERTED_PENDULUM_FMU_NAME)
        copy_verified(pendulum_app, pendulum_target / INVERTED_PENDULUM_APP_NAME)
        copy_verified(pendulum_scene, pendulum_target / "InvertedPendulum.glb")

    if include_local_lateral_motion:
        lateral_root = examples_root / "local-demos" / "bosch-lateral-motion"
        lateral_fmu = lateral_root / LATERAL_MOTION_FMU_NAME
        lateral_app = lateral_root / LATERAL_MOTION_APP_NAME
        lateral_scene = lateral_root / "LateralMotionControl.glb"
        validate_linux_x64_fmu(lateral_fmu)
        validate_local_glb_output_bindings(lateral_scene, lateral_fmu)
        validate_local_fmu_session_app(lateral_app, "lateral-motion", {"crossover-suv.glb"})
        lateral_target = target / "local-demos" / "bosch-lateral-motion" / "linux64"
        lateral_target.mkdir(parents=True, exist_ok=True)
        copy_verified(lateral_fmu, lateral_target / LATERAL_MOTION_FMU_NAME)
        copy_verified(lateral_app, lateral_target / LATERAL_MOTION_APP_NAME)
        copy_verified(lateral_scene, lateral_target / "LateralMotionControl.glb")
        license_path = lateral_root / "LICENSE.txt"
        if license_path.is_file():
            copy_verified(license_path, lateral_target / "LateralMotionControl.LICENSE.txt")

    if include_local_water_tank:
        water_tank_root = examples_root / "local-demos" / "into-cps-water-tank" / "linux64"
        water_tank_fmu = water_tank_root / WATER_TANK_FMU_NAME
        water_tank_app = water_tank_root / WATER_TANK_APP_NAME
        water_tank_scene = water_tank_root / "singlewatertank-20sim.glb"
        water_tank_entries = validate_linux_x64_fmu(water_tank_fmu)
        if "binaries/linux64/SingleWatertank.so" not in water_tank_entries:
            raise ValueError("The water-tank FMU is missing its Linux x86_64 model binary.")
        validate_water_tank_app(water_tank_app)
        validate_local_glb_output_bindings(water_tank_scene, water_tank_fmu)
        water_tank_target = target / "local-demos" / "into-cps-water-tank" / "linux64"
        water_tank_target.mkdir(parents=True, exist_ok=True)
        copy_verified(water_tank_fmu, water_tank_target / WATER_TANK_FMU_NAME)
        copy_verified(water_tank_app, water_tank_target / WATER_TANK_APP_NAME)
        copy_verified(water_tank_scene, water_tank_target / "singlewatertank-20sim.glb")

    if include_local_boptest:
        boptest_root = examples_root / "local-demos" / "boptest-building"
        complex_fmu = boptest_root / BOPTEST_COMPLEX_FMU_NAME
        complex_app = boptest_root / BOPTEST_COMPLEX_APP_NAME
        complex_scene = boptest_root / "BOPTEST-MultizoneOfficeComplexAir.glb"
        complex_license = boptest_root / BOPTEST_COMPLEX_LICENSE_NAME
        validate_boptest_complex_air_fmu(complex_fmu)
        validate_local_glb_output_bindings(complex_scene, complex_fmu)
        if not complex_license.is_file() or "International Building Performance Simulation Association" not in complex_license.read_text(encoding="utf-8"):
            raise ValueError("The local BOPTEST Complex Air FMU must include its upstream redistribution license.")
        validate_webapp_bundle(complex_app)
        with zipfile.ZipFile(complex_app) as archive:
            app_names = set(archive.namelist())
            required_app_files = {
                "index.html",
                "app.js",
                "scene.js",
                "styles.css",
                "vendor/three.module.js",
                "vendor/OrbitControls.js",
                "vendor/RoomEnvironment.js",
            }
            missing_app_files = required_app_files - app_names
            if missing_app_files:
                raise ValueError("The local BOPTEST Complex Air app is incomplete: " + ", ".join(sorted(missing_app_files)))
            app_index = archive.read("index.html").decode("utf-8")
            required_interface_markers = (
                '<main class="app-shell">',
                'id="page-title"',
                'class="page-intro"',
                'class="experiment-controls"',
                'id="simulation-days"',
                'id="run-simulation"',
                'id="scene"',
            )
            if any(marker not in app_index for marker in required_interface_markers):
                raise ValueError("The local BOPTEST Complex Air app is missing its complete demo interface.")
            app_script = archive.read("app.js").decode("utf-8")
            if "createComplexOfficeScene" not in app_script or "GLTFLoader" in app_script or ".glb" in app_script.lower():
                raise ValueError("The local BOPTEST Complex Air app must create its Three.js scene without a GLB.")
            if "playbackControlPosition" not in app_script or "bottom-right" not in app_script:
                raise ValueError("The local BOPTEST Complex Air app must request the bottom-right playback control position.")
        boptest_target.mkdir(parents=True, exist_ok=True)
        copy_verified(complex_fmu, boptest_target / BOPTEST_COMPLEX_FMU_NAME)
        copy_verified(complex_app, boptest_target / BOPTEST_COMPLEX_APP_NAME)
        copy_verified(complex_scene, boptest_target / "BOPTEST-MultizoneOfficeComplexAir.glb")
        copy_verified(complex_license, boptest_target / "BOPTEST-MultizoneOfficeComplexAir.LICENSE.txt")

    if include_local_qfmu:
        qfmu_root = examples_root / "local-demos" / "qfmu"
        qfmu_artifacts = qfmu_root / "artifacts" / "linux64"
        qfmu_license = qfmu_root / QFMU_LICENSE_NAME
        if not qfmu_license.is_file() or "Copyright (c) 2021, Hang Yu" not in qfmu_license.read_text(encoding="utf-8"):
            raise ValueError("The local qFMU demo must include the upstream BSD license.")

        qfmu_target = target / "local-demos" / "qfmu" / "linux64"
        qfmu_target.mkdir(parents=True, exist_ok=True)
        for filename, (expected_inputs, expected_outputs) in QFMU_MODELS.items():
            source = qfmu_artifacts / filename
            validate_qfmu_fmu(source, expected_inputs, expected_outputs)
            copy_verified(source, qfmu_target / filename)
            webapp_name = f"{Path(filename).stem}.webapp.zip"
            webapp = qfmu_artifacts / "webapps" / webapp_name
            validate_qfmu_webapp(webapp)
            copy_verified(webapp, qfmu_target / webapp_name)
        copy_verified(qfmu_license, qfmu_target / QFMU_LICENSE_NAME)

    if include_local_dc_motor:
        motor_root = examples_root / "local-demos" / "dc-motor"
        motor_fmu = motor_root / DC_MOTOR_FMU_NAME
        motor_app = motor_root / DC_MOTOR_APP_NAME
        motor_scene = motor_root / "DC_motor.glb"
        fmugym_license = motor_root / "FMUGym-LICENSE"
        credibility_license = motor_root / "Credibility-LICENSE.md"
        validate_dc_motor_fmu(motor_fmu)
        # Keep the companion GLB for the optional GLB route; the packaged
        # Three.js app uses the FMU's public motor/gear/load positions.
        validate_local_glb_output_bindings(
            motor_scene,
            motor_fmu,
            required_bindings={
                ("out_motor_position", "rotation.x"),
                ("out_gear_position", "rotation.x"),
                ("out_load_position", "rotation.x"),
            },
        )
        validate_dc_motor_app(motor_app)
        if not fmugym_license.is_file() or "MIT License" not in fmugym_license.read_text(encoding="utf-8"):
            raise ValueError("The DC motor FMU must include the upstream FMUGym MIT license.")
        if not credibility_license.is_file() or "BSD 3-Clause License" not in credibility_license.read_text(encoding="utf-8"):
            raise ValueError("The DC motor model must include the upstream Credibility BSD license.")
        motor_target = target / "local-demos" / "dc-motor" / "linux64"
        motor_target.mkdir(parents=True, exist_ok=True)
        copy_verified(motor_fmu, motor_target / DC_MOTOR_FMU_NAME)
        copy_verified(motor_app, motor_target / DC_MOTOR_APP_NAME)
        copy_verified(motor_scene, motor_target / "DC_motor.glb")
        copy_verified(fmugym_license, motor_target / "DC_motor.FMUGym-LICENSE.txt")
        copy_verified(credibility_license, motor_target / "DC_motor.Credibility-LICENSE.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=DEFAULT_EXAMPLES_ROOT,
        help="FMU-Executor/examples directory",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=GATEWAY_ROOT / "fmu-data",
        help="Gateway fmu-data destination",
    )
    parser.add_argument(
        "--include-local-boptest",
        action="store_true",
        help="Also copy the local-only BOPTEST building preview",
    )
    parser.add_argument(
        "--include-local-qfmu",
        action="store_true",
        help="Also copy the four local-only qFMU linear-systems FMUs and companion apps",
    )
    parser.add_argument(
        "--include-local-dc-motor",
        action="store_true",
        help="Also copy the local-only DC motor teaching demo and its app bundle",
    )
    parser.add_argument(
        "--include-local-water-tank",
        action="store_true",
        help="Also copy the local-only INTO-CPS water-tank demo and its app bundle",
    )
    parser.add_argument(
        "--include-local-inverted-pendulum",
        action="store_true",
        help="Also copy the local-only Linux inverted-pendulum FMU and webapp bundle",
    )
    parser.add_argument(
        "--include-local-lateral-motion",
        action="store_true",
        help="Also copy the local-only Bosch lateral-motion FMU and webapp bundle",
    )
    args = parser.parse_args(argv)

    try:
        sync(
            args.examples_root.resolve(),
            args.target.resolve(),
            include_local_boptest=args.include_local_boptest,
            include_local_qfmu=args.include_local_qfmu,
            include_local_dc_motor=args.include_local_dc_motor,
            include_local_water_tank=args.include_local_water_tank,
            include_local_inverted_pendulum=args.include_local_inverted_pendulum,
            include_local_lateral_motion=args.include_local_lateral_motion,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
