"""Read visual companion references from FMI-LS-REF manifests."""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit
import zipfile
import zlib


MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 50 * 1024 * 1024
MANIFEST_PATH = "extra/org.fmi-standard.fmi-ls-ref/fmi-ls-manifest.xml"
MANIFEST_NAME = "org.fmi-standard.fmi-ls-ref"
_FMI_LS_NAMESPACE = "http://fmi-standard.org/fmi-ls-manifest"


def _archive_path(source: str) -> str | None:
    if not source or len(source) > 2048 or "\\" in source or "\x00" in source:
        return None

    parsed = urlsplit(source)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not parsed.path:
        return None

    path = unquote(parsed.path)
    if "\\" in path or "\x00" in path or path.startswith("/"):
        return None

    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(MANIFEST_PATH), path))
    if normalized in {"", ".", ".."} or normalized.startswith(("../", "/")):
        return None
    return normalized


def read_visual_asset(fmu_path: Path) -> tuple[bytes, str, str] | None:
    """Return the declared web app first, or a declared GLB, if present."""
    try:
        with zipfile.ZipFile(fmu_path) as archive:
            manifest_info = archive.getinfo(MANIFEST_PATH)
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                return None
            with archive.open(manifest_info) as source:
                manifest = source.read(MAX_MANIFEST_BYTES + 1)
            if len(manifest) > MAX_MANIFEST_BYTES:
                return None
            lowered = manifest.lower()
            if b"<!doctype" in lowered or b"<!entity" in lowered:
                return None

            root = ET.fromstring(manifest)
            if root.tag.rsplit("}", 1)[-1] != "fmiReferences":
                return None
            if root.attrib.get(f"{{{_FMI_LS_NAMESPACE}}}fmi-ls-name") != MANIFEST_NAME:
                return None

            candidates: list[tuple[str, str]] = []
            for related in root:
                if related.tag.rsplit("}", 1)[-1] != "Related":
                    continue
                path = _archive_path(str(related.attrib.get("source") or ""))
                if path is None:
                    continue
                media_type = str(related.attrib.get("type") or "").split(";", 1)[0].strip().lower()
                lowered_path = path.lower()
                if lowered_path.endswith(".webapp.zip") and media_type in {
                    "application/zip", "application/x-zip-compressed",
                }:
                    candidates.append((path, "threejs-app"))
                elif lowered_path.endswith(".glb") and media_type in {
                    "model/gltf-binary", "application/octet-stream",
                }:
                    candidates.append((path, "glb"))

            candidates.sort(key=lambda candidate: candidate[1] != "threejs-app")
            names = archive.namelist()
            for path, asset_type in candidates:
                if names.count(path) != 1:
                    continue
                info = archive.getinfo(path)
                if info.is_dir() or info.file_size > MAX_ASSET_BYTES:
                    continue
                with archive.open(info) as source:
                    content = source.read(MAX_ASSET_BYTES + 1)
                if len(content) <= MAX_ASSET_BYTES:
                    return content, asset_type, "fmi-ls-ref"
    except (OSError, KeyError, ValueError, ET.ParseError, zipfile.BadZipFile, RuntimeError, EOFError, zlib.error):
        return None
    return None
