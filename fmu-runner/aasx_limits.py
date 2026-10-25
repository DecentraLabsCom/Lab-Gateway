"""Resource limits for provider-supplied AASX OPC packages."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable


MAX_AASX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_AASX_ARCHIVE_ENTRIES = 10_000
MAX_AASX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_AASX_ENVIRONMENT_PART_BYTES = 16 * 1024 * 1024
MAX_AASX_RELATIONSHIP_PART_BYTES = 1 * 1024 * 1024


class AasxImportError(Exception):
    """Base class for AASX inputs that cannot safely be imported."""


class AasxLimitError(AasxImportError):
    """Raised when an AASX archive exceeds an explicit resource bound."""


class AasxInvalidContentError(AasxImportError):
    """Raised when an AASX environment contains unsupported unsafe content."""


def validate_aasx_upload_size(size: int) -> None:
    if size > MAX_AASX_UPLOAD_BYTES:
        raise AasxLimitError(
            f"AASX upload exceeds the {MAX_AASX_UPLOAD_BYTES // (1024 * 1024)} MiB limit"
        )


def validate_aasx_archive(infos: Iterable[zipfile.ZipInfo], compressed_size: int) -> list[zipfile.ZipInfo]:
    """Check ZIP metadata before any compressed member is expanded."""
    validate_aasx_upload_size(compressed_size)
    entries = list(infos)
    if len(entries) > MAX_AASX_ARCHIVE_ENTRIES:
        raise AasxLimitError("AASX archive contains too many ZIP entries")

    seen_names: set[str] = set()
    expanded_size = 0
    for info in entries:
        if info.filename in seen_names:
            raise AasxInvalidContentError("AASX archive contains duplicate ZIP entry names")
        seen_names.add(info.filename)
        expanded_size += info.file_size
        if expanded_size > MAX_AASX_EXPANDED_BYTES:
            raise AasxLimitError("AASX expanded contents exceed the 256 MiB limit")

    return entries
