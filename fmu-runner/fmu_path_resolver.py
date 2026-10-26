"""Resolve FMU access keys safely within the configured data directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional


class FmuPathResolutionError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

def _is_within_base(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def resolve_fmu_path(
    fmu_filename: str,
    fmu_data_path: str | Path,
    *,
    validate_access_key: Callable[[str], str],
) -> Path:
    """Resolve an authorised FMU access key below the configured data root."""
    if len(str(fmu_filename)) > 255:
        raise FmuPathResolutionError(400, "Invalid FMU file key")
    fmu_filename = validate_access_key(fmu_filename)
    base = Path(fmu_data_path).resolve()
    if not base.is_dir():
        raise FmuPathResolutionError(503, "FMU data directory is unavailable")

    segments = fmu_filename.split("/")
    if len(segments) > 1:
        # Explicit access keys may address files nested below fmu-data (for
        # example, local-demos/<demo>/linux64/model.fmu). Walk directory
        # entries instead of joining untrusted input, and reject symlinks that
        # resolve outside the configured FMU root.
        current = base
        for index, segment in enumerate(segments):
            try:
                entry = next(
                    (
                        candidate
                        for candidate in current.iterdir()
                        if os.path.normcase(candidate.name) == os.path.normcase(segment)
                    ),
                    None,
                )
            except OSError:
                entry = None
            if entry is None:
                raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")
            try:
                current = entry.resolve(strict=True)
            except OSError:
                raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")
            if not _is_within_base(base, current):
                raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")
            if index < len(segments) - 1 and not current.is_dir():
                raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")
        if current.is_file():
            return current
        raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")

    def _trusted_match(directory: Path) -> Optional[Path]:
        """Return a matching file already discovered under the trusted root."""
        try:
            entries = directory.iterdir()
        except OSError:
            return None
        for entry in entries:
            # Compare against the directory entry name; never construct a path
            # by appending the request value to a filesystem path.
            if os.path.normcase(entry.name) != os.path.normcase(fmu_filename):
                continue
            try:
                resolved = entry.resolve(strict=True)
            except OSError:
                continue
            if _is_within_base(base, resolved) and resolved.is_file():
                return resolved
        return None

    # Direct match.  The path comes from directory enumeration, not user input.
    direct = _trusted_match(base)
    if direct is not None:
        return direct

    # Search in provider sub-directories (fmu-data/<provider-wallet>/file.fmu).
    for child in base.iterdir():
        if child.is_dir():
            candidate = _trusted_match(child)
            if candidate is not None:
                return candidate
    raise FmuPathResolutionError(404, f"FMU file not found: {fmu_filename}")
