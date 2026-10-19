"""Sync canonical example FMUs into Gateway's local development data directory."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES_ROOT = GATEWAY_ROOT.parent / "FMU-Executor" / "examples"
REFERENCE_FMU_NAMES = {
    "BinaryClockTest.fmu",
    "BouncingBall.fmu",
    "Dahlquist.fmu",
    "Feedthrough.fmu",
    "Stair.fmu",
    "StateSpace.fmu",
    "VanDerPol.fmu",
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


def sync(examples_root: Path, target: Path) -> None:
    reference_root = examples_root / "reference-fmus"
    canonical_reference_fmus = {
        path.name: path for path in reference_root.glob("*.fmu") if path.is_file()
    }
    missing = REFERENCE_FMU_NAMES - canonical_reference_fmus.keys()
    if missing:
        raise FileNotFoundError(
            "Canonical reference FMUs are missing: " + ", ".join(sorted(missing))
        )

    target.mkdir(parents=True, exist_ok=True)
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

    smart_factory_root = examples_root / "smart-factory-cell"
    linux_fmu = smart_factory_root / "SmartFactoryCell-linux64.fmu"
    scene = smart_factory_root / "smart-factory-cell.glb"
    license_file = smart_factory_root / "LICENSE.txt"
    validate_linux_x64_fmu(linux_fmu)
    with zipfile.ZipFile(linux_fmu) as archive:
        embedded_scene = archive.read("resources/smart-factory-cell.glb")
    if embedded_scene != scene.read_bytes():
        raise ValueError("The Smart Factory FMU's embedded scene differs from its companion GLB.")

    copy_verified(linux_fmu, target / "SmartFactoryCell.fmu")
    copy_verified(scene, target / "SmartFactoryCell.glb")
    copy_verified(license_file, target / "SmartFactoryCell.LICENSE.txt")


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
    args = parser.parse_args(argv)

    try:
        sync(args.examples_root.resolve(), args.target.resolve())
    except (FileNotFoundError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
