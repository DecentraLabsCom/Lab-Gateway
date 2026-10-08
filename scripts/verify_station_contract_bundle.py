#!/usr/bin/env python3
"""Verify a station's vendored Gateway schemas against an immutable source pin."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Mapping, Optional


DEFAULT_LOCK = Path("contracts/station/schema-bundle.lock.json")
_REPOSITORY = "DecentraLabsCom/Lab-Gateway"


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError(f"{field} must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} must be a relative POSIX path")
    return path.as_posix()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(canonical_root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(["git", "-C", str(canonical_root), *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("canonical Gateway checkout could not be inspected") from exc


def _load_lock(lock_path: Path) -> Mapping[str, Any]:
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("station contract bundle lock is invalid") from exc
    if (
        not isinstance(lock, dict)
        or lock.get("schemaVersion") != 1
        or lock.get("repository") != _REPOSITORY
        or not isinstance(lock.get("commit"), str)
        or len(lock["commit"]) != 40
        or any(char not in "0123456789abcdef" for char in lock["commit"])
        or not isinstance(lock.get("files"), list)
        or not lock["files"]
    ):
        raise ValueError("station contract bundle lock is invalid")
    return lock


def verify_bundle(
    station_root: Path,
    lock_path: Path,
    canonical_root: Optional[Path] = None,
) -> None:
    station_root = station_root.resolve()
    contract_root = station_root / "contracts" / "station"
    if not lock_path.is_absolute():
        lock_path = station_root / lock_path
    lock = _load_lock(lock_path)

    mappings: list[tuple[str, str, str]] = []
    sources: set[str] = set()
    targets: set[str] = set()
    for entry in lock["files"]:
        if not isinstance(entry, dict):
            raise ValueError("station contract bundle lock contains an invalid file entry")
        source = _relative_path(entry.get("source"), "source")
        target = _relative_path(entry.get("target"), "target")
        digest = entry.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or source in sources
            or target in targets
        ):
            raise ValueError("station contract bundle lock contains an invalid file entry")
        sources.add(source)
        targets.add(target)
        mappings.append((source, target, digest))

    bundle_targets = {target.removeprefix("gateway-contracts/") for _, target, _ in mappings if target.startswith("gateway-contracts/")}
    actual_bundle_targets = {
        path.relative_to(contract_root / "gateway-contracts").as_posix()
        for path in (contract_root / "gateway-contracts").rglob("*")
        if path.is_file()
    }
    if bundle_targets != actual_bundle_targets:
        raise ValueError("station contract bundle file set differs from its lock")

    for _, target, expected_digest in mappings:
        local_path = contract_root.joinpath(*PurePosixPath(target).parts)
        try:
            resolved = local_path.resolve(strict=True)
            resolved.relative_to(contract_root.resolve())
            local_bytes = resolved.read_bytes()
        except (OSError, ValueError) as exc:
            raise ValueError(f"station contract bundle is missing or unsafe: {target}") from exc
        if _sha256(local_bytes) != expected_digest:
            raise ValueError(f"station contract bundle digest mismatch: {target}")

    if canonical_root is None:
        return
    canonical_root = canonical_root.resolve()
    try:
        revision = _git(canonical_root, "rev-parse", "HEAD").decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("canonical Gateway checkout has an invalid revision") from exc
    if revision != lock["commit"]:
        raise ValueError("canonical Gateway revision does not match the station contract pin")

    try:
        tracked = _git(
            canonical_root,
            "ls-tree",
            "-r",
            "--name-only",
            lock["commit"],
            "--",
            "contracts/station",
            "docs/station-test-parity.json",
        ).decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("canonical Gateway contract paths are invalid") from exc
    if set(tracked) != sources:
        raise ValueError("canonical Gateway contract file set differs from the station pin")

    for source, target, expected_digest in mappings:
        try:
            source_bytes = _git(canonical_root, "show", f"{lock['commit']}:{source}")
        except ValueError as exc:
            raise ValueError(f"canonical Gateway contract is missing: {source}") from exc
        if _sha256(source_bytes) != expected_digest:
            raise ValueError(f"canonical Gateway source digest mismatch: {source} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--station-root", type=Path, default=Path.cwd())
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--canonical-root", type=Path)
    args = parser.parse_args()
    try:
        verify_bundle(args.station_root, args.lock, args.canonical_root)
    except ValueError as exc:
        parser.error(str(exc))
    print("Station contract bundle matches its pinned Gateway source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
