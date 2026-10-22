"""Sync canonical FMU examples into Gateway's ignored development data directory.

The six reference FMUs and Smart Warehouse are synced by default. BOPTEST,
qFMU and other new demo artifacts remain local-only; the optional BOPTEST and
qFMU previews require explicit flags. This script never adds demo files to
Gateway images or release packages.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


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
REQUIRED_APP_PROTOCOL_MESSAGES = {
    "decentralabs:digital-twin-host-ready",
    "decentralabs:digital-twin-ready",
    "decentralabs:digital-twin-error",
    "decentralabs:fmi-sample",
    "decentralabs:fmi-reset",
    "decentralabs:fmi-simulation-state",
    "decentralabs:fmi-samples",
}
BOPTEST_FMU_NAME = "BOPTEST-MultizoneOfficeSimpleHydronic.fmu"
BOPTEST_APP_NAME = "BOPTEST-MultizoneOfficeSimpleHydronic.webapp.zip"
BOPTEST_LICENSE_NAME = "BOPTEST.LICENSE.txt"
BOPTEST_ZONES = ("Nz", "Sz")
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


def copy_verified(origin: Path, destination: Path) -> None:
    if not origin.is_file():
        raise FileNotFoundError(f"Canonical example asset not found: {origin}")
    shutil.copy2(origin, destination)
    if sha256(origin) != sha256(destination):
        raise OSError(f"Copy verification failed for {destination}")
    print(f"Synced {origin.name} -> {destination}")


def validate_boptest_fmu(path: Path) -> set[str]:
    names = validate_linux_x64_fmu(path)
    required_binaries = {"binaries/linux64/wrapped.so"}
    missing_binaries = required_binaries - names
    if missing_binaries:
        raise ValueError(
            f"BOPTEST office FMU is missing its Linux x86_64 runtime libraries: {', '.join(sorted(missing_binaries))}"
        )

    try:
        with zipfile.ZipFile(path) as archive:
            description = ET.fromstring(archive.read("modelDescription.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ValueError(f"Invalid BOPTEST office FMU model description: {error}") from error

    if description.attrib.get("fmiVersion") != "2.0":
        raise ValueError("BOPTEST office FMU must use FMI 2.0.")
    if description.find("{*}CoSimulation") is None:
        raise ValueError("BOPTEST office FMU must expose FMI Co-Simulation.")

    variables = description.find("{*}ModelVariables")
    if variables is None:
        raise ValueError("BOPTEST office FMU has no model variables.")
    variable_names = {
        element.attrib.get("name")
        for element in variables
        if element.attrib.get("causality") == "output"
    }
    required_outputs = {
        f"structure_reaTZon{zone}_y" for zone in BOPTEST_ZONES
    } | {
        f"structure_reaCO2Zon{zone}_y" for zone in BOPTEST_ZONES
    } | {
        f"heating_cooling_reaPFcu{zone}_y" for zone in BOPTEST_ZONES
    } | {
        f"ventilation_reaPAhuSup{zone}_y" for zone in BOPTEST_ZONES
    }
    required_outputs.update(
        {
            "heating_cooling_reaPProHea_y",
            "heating_cooling_reaPProCoo_y",
            "heating_cooling_reaPPumProHea_y",
            "heating_cooling_reaPPumProCoo_y",
            "weaSta_reaWeaTDryBul_y",
            "weaSta_reaWeaHGloHor_y",
        }
    )
    missing_outputs = required_outputs - variable_names
    if missing_outputs:
        raise ValueError(
            "BOPTEST office FMU is missing required scene signals: "
            + ", ".join(sorted(missing_outputs))
        )

    required_inputs = {
        f"bms_oveTZonSet{boundary}{zone}_{suffix}"
        for zone in BOPTEST_ZONES
        for boundary in ("Min", "Max")
        for suffix in ("u", "activate")
    }
    input_names = {
        element.attrib.get("name")
        for element in variables
        if element.attrib.get("causality") == "input"
    }
    missing_inputs = required_inputs - input_names
    if missing_inputs:
        raise ValueError(
            "BOPTEST office FMU is missing its zone setpoint controls: "
            + ", ".join(sorted(missing_inputs))
        )

    required_resources = {
        "resources/weather.csv",
        "resources/setpoints.csv",
        "resources/internalGains.csv",
        "resources/occupancy.csv",
        "resources/prices.csv",
        "resources/emissions.csv",
    }
    missing_resources = required_resources - names
    if missing_resources:
        raise ValueError(
            "BOPTEST office FMU is missing its self-contained scenario resources: "
            + ", ".join(sorted(missing_resources))
        )
    return names


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
    inputs = {
        variable.attrib.get("name")
        for variable in variables
        if variable.attrib.get("causality") == "input"
    }
    outputs = {
        variable.attrib.get("name")
        for variable in variables
        if variable.attrib.get("causality") == "output"
    }
    if inputs != expected_inputs or outputs != expected_outputs:
        raise ValueError(
            f"Unexpected qFMU variables in {path.name}: inputs={sorted(inputs)}, "
            f"outputs={sorted(outputs)}"
        )


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
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    # Remove stale local copies of retired examples from existing workspaces.
    for obsolete_name in (
        "SmartFactoryCell.fmu",
        "SmartFactoryCell.glb",
        "SmartFactoryCell.LICENSE.txt",
        "Dahlquist.fmu",
        "BOPTEST-MultizoneOfficeComplexAir.fmu",
        "BOPTEST-MultizoneOfficeComplexAir.webapp.zip",
        "BOPTEST-MultizoneOfficeComplexAir.LICENSE.txt",
        "BOPTEST-MultizoneOfficeSimpleAir.fmu",
        "BOPTEST-SimpleAir-TestPatch.fmu",
        "BOPTEST-SimpleAir-TestPatch2.fmu",
    ):
        (target / obsolete_name).unlink(missing_ok=True)
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
    with zipfile.ZipFile(warehouse_app) as archive:
        app_names = set(archive.namelist())
        if not {"index.html", "app.js", "scene.js"}.issubset(app_names):
            raise ValueError("The Smart Warehouse app bundle is missing its procedural scene modules.")
        if "warehouse.glb" in app_names or "vendor/GLTFLoader.js" in app_names:
            raise ValueError("The Smart Warehouse Three.js app must build its scene independently from the GLB.")
        app_script = archive.read("app.js").decode("utf-8")
        if "createSmartWarehouseScene" not in app_script or "scene.js" not in app_script:
            raise ValueError("The Smart Warehouse app bundle does not load its procedural scene module.")
        if any(message not in app_script for message in REQUIRED_APP_PROTOCOL_MESSAGES):
            raise ValueError("The Smart Warehouse app bundle is missing the Marketplace host protocol.")

    copy_verified(warehouse_fmu, target / "SmartWarehouseCell.fmu")
    copy_verified(warehouse_scene, target / "SmartWarehouseCell.glb")
    copy_verified(warehouse_app, target / "SmartWarehouseCell.webapp.zip")
    copy_verified(warehouse_license, target / "SmartWarehouseCell.LICENSE.txt")

    if include_local_boptest:
        boptest_root = examples_root / "boptest-building"
        boptest_fmu = boptest_root / BOPTEST_FMU_NAME
        boptest_app = boptest_root / BOPTEST_APP_NAME
        boptest_license = boptest_root / BOPTEST_LICENSE_NAME
        validate_boptest_fmu(boptest_fmu)
        if not boptest_license.is_file() or "International Building Performance Simulation Association" not in boptest_license.read_text(encoding="utf-8"):
            raise ValueError("The local BOPTEST FMU must include the upstream v0.9.0 redistribution license.")
        with zipfile.ZipFile(boptest_app) as archive:
            app_names = set(archive.namelist())
            required_app_files = {
                "index.html",
                "app.js",
                "scene.js",
                "styles.css",
                "vendor/three.module.js",
                "vendor/OrbitControls.js",
            }
            missing_app_files = required_app_files - app_names
            if missing_app_files:
                raise ValueError("The local BOPTEST Three.js app is incomplete: " + ", ".join(sorted(missing_app_files)))
            app_script = archive.read("app.js").decode("utf-8")
            if "createBuildingScene" not in app_script or "GLTFLoader" in app_script:
                raise ValueError("The local BOPTEST app must build its own scene with Three.js and not load a GLB.")
            if any(message not in app_script for message in REQUIRED_APP_PROTOCOL_MESSAGES):
                raise ValueError("The local BOPTEST app bundle is missing the Marketplace host protocol.")
        copy_verified(boptest_fmu, target / BOPTEST_FMU_NAME)
        copy_verified(boptest_app, target / BOPTEST_APP_NAME)
        copy_verified(boptest_license, target / "BOPTEST-MultizoneOfficeSimpleHydronic.LICENSE.txt")

        complex_fmu = boptest_root / BOPTEST_COMPLEX_FMU_NAME
        complex_app = boptest_root / BOPTEST_COMPLEX_APP_NAME
        complex_license = boptest_root / BOPTEST_COMPLEX_LICENSE_NAME
        validate_boptest_complex_air_fmu(complex_fmu)
        if not complex_license.is_file() or "International Building Performance Simulation Association" not in complex_license.read_text(encoding="utf-8"):
            raise ValueError("The local BOPTEST Complex Air FMU must include its upstream redistribution license.")
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
            app_script = archive.read("app.js").decode("utf-8")
            if "createComplexOfficeScene" not in app_script or "GLTFLoader" in app_script or ".glb" in app_script.lower():
                raise ValueError("The local BOPTEST Complex Air app must create its Three.js scene without a GLB.")
            if any(message not in app_script for message in REQUIRED_APP_PROTOCOL_MESSAGES):
                raise ValueError("The local BOPTEST Complex Air app is missing the Marketplace host protocol.")
        copy_verified(complex_fmu, target / BOPTEST_COMPLEX_FMU_NAME)
        copy_verified(complex_app, target / BOPTEST_COMPLEX_APP_NAME)
        copy_verified(complex_license, target / "BOPTEST-MultizoneOfficeComplexAir.LICENSE.txt")

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
        copy_verified(qfmu_license, qfmu_target / QFMU_LICENSE_NAME)


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
        help="Also copy the four local-only qFMU linear-systems examples",
    )
    args = parser.parse_args(argv)

    try:
        sync(
            args.examples_root.resolve(),
            args.target.resolve(),
            include_local_boptest=args.include_local_boptest,
            include_local_qfmu=args.include_local_qfmu,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
