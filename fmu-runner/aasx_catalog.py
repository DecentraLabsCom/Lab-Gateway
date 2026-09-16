"""Durable metadata for provider-managed AASX associations.

BaSyx owns the AAS shells and submodels.  This catalog only records the
laboratory association and the resource IDs needed to serialize or delete
those resources; it never persists the uploaded AASX bytes.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def _validate_lab_id(lab_id: str) -> str:
    value = str(lab_id or "").strip()
    if _LAB_ID_RE.fullmatch(value) is None:
        raise ValueError("invalid AASX laboratory ID")
    return value


def _unique_string_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ))


def _display_filename(lab_id: str, filename: Optional[str]) -> str:
    raw = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    raw = _SAFE_FILENAME_RE.sub("_", raw)
    if not raw or raw in {".", ".."} or not raw.lower().endswith(".aasx"):
        return f"{lab_id}.aasx"
    return raw if len(raw) <= 255 else f"{raw[:251]}.aasx"


class AasxPackageCatalog:
    """Keep one lightweight AASX association record per laboratory."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def _base_path(self) -> Path:
        return self.base_path.resolve()

    def _metadata_path(self, lab_id: str) -> Path:
        safe_lab_id = _validate_lab_id(lab_id)
        base = self._base_path()
        candidate = (base / f"{safe_lab_id}.aasx.json").resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise ValueError("invalid AASX catalog path") from error
        return candidate

    def _legacy_archive_path(self, lab_id: str) -> Path:
        safe_lab_id = _validate_lab_id(lab_id)
        base = self._base_path()
        candidate = (base / f"{safe_lab_id}.aasx").resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise ValueError("invalid AASX catalog path") from error
        return candidate

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _normalize_package(package: Any, expected_lab_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        if not isinstance(package, dict):
            return None
        try:
            lab_id = _validate_lab_id(package.get("labId", ""))
        except (ValueError, TypeError):
            return None
        if expected_lab_id is not None and lab_id != expected_lab_id:
            return None
        try:
            size = max(0, int(package.get("size", 0)))
        except (TypeError, ValueError):
            size = 0
        normalized = dict(package)
        normalized.update({
            "labId": lab_id,
            "filename": _display_filename(lab_id, package.get("filename")),
            "size": size,
            "storage": "basyx",
            "archiveStored": False,
            "shellIds": _unique_string_values(package.get("shellIds")),
            "submodelIds": _unique_string_values(package.get("submodelIds")),
        })
        checksum = package.get("sha256")
        normalized["sha256"] = checksum if isinstance(checksum, str) else ""
        return normalized

    def record(
        self,
        *,
        lab_id: str,
        filename: Optional[str],
        content: bytes,
        sync_result: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record upload metadata without retaining the uploaded archive."""
        safe_lab_id = _validate_lab_id(lab_id)
        if not isinstance(content, bytes) or not content:
            raise ValueError("AASX package content is empty")

        result = sync_result if isinstance(sync_result, Mapping) else {}
        shell_ids = _unique_string_values(result.get("uploadedAasIds"))
        if not shell_ids:
            shell_ids = _unique_string_values([result.get("aasId")])
        package = {
            "labId": safe_lab_id,
            "filename": _display_filename(safe_lab_id, filename),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "storage": "basyx",
            "archiveStored": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "shellIds": shell_ids,
            "submodelIds": _unique_string_values(result.get("uploadedSubmodelIds")),
        }
        metadata_path = self._metadata_path(safe_lab_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            metadata_path,
            json.dumps(package, indent=2, sort_keys=True).encode("utf-8"),
        )
        return package

    def get(self, lab_id: str) -> Optional[dict[str, Any]]:
        safe_lab_id = _validate_lab_id(lab_id)
        metadata_path = self._metadata_path(safe_lab_id)
        if not metadata_path.is_file():
            return None
        try:
            package = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError, TypeError):
            return None
        return self._normalize_package(package, expected_lab_id=safe_lab_id)

    def list_packages(self) -> list[dict[str, Any]]:
        base = self._base_path()
        if not base.is_dir():
            return []
        packages: list[dict[str, Any]] = []
        for metadata_path in base.glob("*.aasx.json"):
            try:
                package = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, AttributeError, TypeError):
                continue
            package = self._normalize_package(package)
            if package is None:
                continue
            packages.append(package)
        return sorted(packages, key=lambda package: str(package.get("labId", "")))

    def delete(self, lab_id: str) -> bool:
        metadata_path = self._metadata_path(lab_id)
        legacy_archive_path = self._legacy_archive_path(lab_id)
        existed = metadata_path.is_file() or legacy_archive_path.is_file()
        metadata_path.unlink(missing_ok=True)
        # Remove archives written by versions that predated this catalog.
        legacy_archive_path.unlink(missing_ok=True)
        return existed


__all__ = ["AasxPackageCatalog"]
