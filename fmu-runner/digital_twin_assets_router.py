"""Provider-managed public GLB storage for Smart Factory scenes."""

import hashlib
import hmac
import io
import json
import os
import re
import struct
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin
import zipfile

import httpx
from fastapi import APIRouter, HTTPException, Request


_MAX_SCENE_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_ARCHIVE_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_ASSET_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_UNPACKED_BYTES = 120 * 1024 * 1024
_MAX_WEBAPP_FILES = 300
_GLB_HEADER = struct.Struct("<4sII")
_CHUNK_HEADER = struct.Struct("<II")
_GLB_MAGIC = b"glTF"
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942


def _validate_glb(content: bytes) -> dict[str, Any]:
    if len(content) < _GLB_HEADER.size + _CHUNK_HEADER.size:
        raise HTTPException(status_code=400, detail="GLB file is incomplete")
    if len(content) > _MAX_SCENE_BYTES:
        raise HTTPException(status_code=413, detail="GLB exceeds the 50 MiB limit")

    magic, version, total_length = _GLB_HEADER.unpack_from(content, 0)
    if magic != _GLB_MAGIC or version != 2 or total_length != len(content):
        raise HTTPException(status_code=400, detail="Only valid glTF 2.0 binary scenes are accepted")

    cursor = _GLB_HEADER.size
    chunk_index = 0
    document: dict[str, Any] | None = None
    while cursor < total_length:
        if total_length - cursor < _CHUNK_HEADER.size:
            raise HTTPException(status_code=400, detail="GLB chunk header is incomplete")
        chunk_length, chunk_type = _CHUNK_HEADER.unpack_from(content, cursor)
        cursor += _CHUNK_HEADER.size
        chunk_end = cursor + chunk_length
        if chunk_length % 4 != 0 or chunk_end > total_length:
            raise HTTPException(status_code=400, detail="GLB chunk length is invalid")
        if chunk_index == 0:
            if chunk_type != _JSON_CHUNK:
                raise HTTPException(status_code=400, detail="GLB JSON chunk must be first")
            try:
                parsed = json.loads(content[cursor:chunk_end].decode("utf-8").rstrip(" \t\r\n\0"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=400, detail="GLB JSON chunk is invalid") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="GLB scene description is invalid")
            document = parsed
        elif chunk_index == 1 and chunk_type != _BIN_CHUNK:
            raise HTTPException(status_code=400, detail="GLB contains an unsupported chunk")
        elif chunk_index > 1:
            raise HTTPException(status_code=400, detail="GLB contains unsupported extra chunks")
        cursor = chunk_end
        chunk_index += 1

    asset = document.get("asset") if isinstance(document, dict) else None
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise HTTPException(status_code=400, detail="Only glTF 2.0 binary scenes are accepted")

    for collection_name in ("buffers", "images"):
        collection = document.get(collection_name, [])
        if not isinstance(collection, list):
            raise HTTPException(status_code=400, detail="GLB resource declarations are invalid")
        for resource in collection:
            if not isinstance(resource, dict):
                raise HTTPException(status_code=400, detail="GLB resource declaration is invalid")
            uri = resource.get("uri")
            if uri is not None and (not isinstance(uri, str) or not uri.startswith("data:")):
                raise HTTPException(status_code=400, detail="GLB must not reference external resources")
    return document


def _validate_webapp_archive(content: bytes) -> dict[str, bytes]:
    if not content:
        raise HTTPException(status_code=400, detail="Three.js application archive is empty")
    if len(content) > _MAX_WEBAPP_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="Three.js application archive exceeds 50 MiB")

    files: dict[str, bytes] = {}
    normalized_names: set[str] = set()
    unpacked_size = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > _MAX_WEBAPP_FILES + 32:
                raise HTTPException(status_code=413, detail="Three.js application has too many files")
            for entry in entries:
                raw_name = entry.filename
                if not raw_name or "\\" in raw_name or raw_name.startswith("/"):
                    raise HTTPException(status_code=400, detail="Application archive contains an unsafe path")
                path = PurePosixPath(raw_name)
                if any(part in ("", ".", "..") for part in path.parts) or path.is_absolute():
                    raise HTTPException(status_code=400, detail="Application archive contains an unsafe path")
                if len(path.parts) > 8:
                    raise HTTPException(status_code=400, detail="Application archive path is too deep")
                if any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", part) is None for part in path.parts):
                    raise HTTPException(status_code=400, detail="Application archive contains an unsupported filename")
                if entry.flag_bits & 0x1:
                    raise HTTPException(status_code=400, detail="Encrypted application archives are not supported")
                mode = (entry.external_attr >> 16) & 0o170000
                if mode not in (0, 0o100000, 0o040000):
                    raise HTTPException(status_code=400, detail="Application archive must not contain links or special files")
                if entry.is_dir():
                    continue
                name = path.as_posix()
                folded_name = name.casefold()
                if folded_name in normalized_names:
                    raise HTTPException(status_code=400, detail="Application archive contains duplicate paths")
                normalized_names.add(folded_name)
                if path.suffix.lower() not in {
                    ".html", ".js", ".mjs", ".css", ".json", ".wasm", ".glb", ".gltf",
                    ".bin", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff", ".woff2",
                    ".ttf", ".ico", ".txt",
                }:
                    raise HTTPException(status_code=400, detail="Application archive contains an unsupported file type")
                if entry.file_size > _MAX_WEBAPP_ASSET_BYTES:
                    raise HTTPException(status_code=413, detail="A Three.js application asset exceeds 50 MiB")
                unpacked_size += entry.file_size
                if unpacked_size > _MAX_WEBAPP_UNPACKED_BYTES:
                    raise HTTPException(status_code=413, detail="Three.js application expands beyond 120 MiB")
                files[name] = archive.read(entry)
    except HTTPException:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Three.js application archive is invalid") from exc

    index_html = files.get("index.html")
    if index_html is None:
        raise HTTPException(status_code=400, detail="Three.js application must contain a root index.html")
    try:
        html = index_html.decode("utf-8").lower()
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Three.js application index.html must use UTF-8") from exc
    if "<html" not in html or "<base" in html:
        raise HTTPException(status_code=400, detail="Three.js application index.html is invalid or uses a base URL")
    if re.search(r"(?:src|href)\s*=\s*['\"](?:https?:|//|/)", html):
        raise HTTPException(status_code=400, detail="Three.js application must use bundled relative assets")
    if len(files) > _MAX_WEBAPP_FILES:
        raise HTTPException(status_code=413, detail="Three.js application has too many files")
    return files


def _store_scene(root: Path, lab_id: str, content: bytes) -> dict[str, Any]:
    _validate_glb(content)
    digest = hashlib.sha256(content).hexdigest()
    try:
        root.mkdir(parents=True, exist_ok=True)
        lab_directory = (root / lab_id).resolve()
        if not lab_directory.is_relative_to(root):
            raise HTTPException(status_code=400, detail="Invalid laboratory asset path")
        lab_directory.mkdir(parents=True, exist_ok=True)
        target = lab_directory / f"{digest}.glb"
        if not target.exists():
            descriptor, temporary_name = tempfile.mkstemp(prefix=".scene-", suffix=".tmp", dir=lab_directory)
            try:
                with os.fdopen(descriptor, "wb") as temporary_file:
                    temporary_file.write(content)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.chmod(temporary_name, 0o644)
                os.replace(temporary_name, target)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Digital twin asset storage is unavailable") from exc

    return {
        "success": True,
        "path": f"/digital-twin-scenes/{lab_id}/{digest}.glb",
        "sha256": digest,
        "size": len(content),
    }


def _store_webapp(root: Path, lab_id: str, content: bytes) -> dict[str, Any]:
    files = _validate_webapp_archive(content)
    digest = hashlib.sha256(content).hexdigest()
    try:
        lab_directory = root / lab_id
        lab_directory.mkdir(parents=True, exist_ok=True)
        if lab_directory.is_symlink():
            raise HTTPException(status_code=400, detail="Digital twin application storage path is invalid")
        apps_root = lab_directory.resolve()
        if not apps_root.is_relative_to(root):
            raise HTTPException(status_code=400, detail="Digital twin application storage path is invalid")
        apps_root.mkdir(parents=True, exist_ok=True)
        target = apps_root / digest
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix=f".{digest}.", dir=apps_root) as temporary_name:
                temporary_root = Path(temporary_name)
                for name, payload in files.items():
                    destination = temporary_root.joinpath(*PurePosixPath(name).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        output.write(payload)
                    os.chmod(destination, 0o644)
                try:
                    os.replace(temporary_root, target)
                except OSError:
                    if not target.is_dir():
                        raise
        if target.is_symlink() or not target.is_dir():
            raise HTTPException(status_code=400, detail="Digital twin application storage path is invalid")
        # OpenResty serves the immutable files as a separate, read-only user.
        pending_directories = [target]
        while pending_directories:
            directory = pending_directories.pop()
            os.chmod(directory, 0o755)
            for child in directory.iterdir():
                if child.is_symlink():
                    raise HTTPException(status_code=400, detail="Digital twin application storage path is invalid")
                if child.is_dir():
                    pending_directories.append(child)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Digital twin application storage is unavailable") from exc

    return {
        "success": True,
        "path": f"/digital-twin-apps/{lab_id}/{digest}/index.html",
        "contentType": "text/html",
        "sha256": digest,
        "size": len(content),
        "files": len(files),
    }


def _validate_asset_type(asset_type: Any) -> str:
    normalized = str(asset_type or "").strip().lower()
    if normalized not in {"glb", "threejs-app"}:
        raise HTTPException(status_code=400, detail="assetType must be glb or threejs-app")
    return normalized


def _validate_access_key(access_key: Any) -> str:
    if not isinstance(access_key, str) or len(access_key) > 512 or not access_key.lower().endswith(".fmu"):
        raise HTTPException(status_code=400, detail="Invalid FMU access key")
    segments = access_key.split("/")
    if any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", segment) is None
        for segment in segments
    ):
        raise HTTPException(status_code=400, detail="Invalid FMU access key")
    return access_key


async def _read_limited_response(response: httpx.Response, limit: int, label: str) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(status_code=413, detail=f"Companion {label} exceeds the size limit")
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Station returned an invalid digital twin asset response") from exc

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"Companion {label} exceeds the size limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_limited_request(request: Request, limit: int, *, label: str) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(status_code=413, detail=f"{label} exceeds the request size limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length is invalid") from exc

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"{label} exceeds the request size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def create_digital_twin_assets_router(
    *,
    asset_root: Path,
    lab_manager_token: str,
    fmu_backend_mode: str = "station",
    fmu_data_root: Path = Path("/app/fmu-data"),
    resolve_local_fmu_path=None,
    station_base_url: str = "",
    station_internal_token: str = "",
    station_request_timeout: float = 10,
) -> APIRouter:
    router = APIRouter()
    root = Path(asset_root).expanduser().resolve()

    @router.put("/admin/digital-twin-assets/{lab_id}")
    async def upload_asset(lab_id: str, request: Request):
        if not lab_id.isdigit() or len(lab_id) > 78:
            raise HTTPException(status_code=400, detail="Invalid laboratory ID")
        if not lab_manager_token:
            raise HTTPException(status_code=503, detail="Digital twin asset upload is not configured")
        provided_token = request.headers.get("x-digital-twin-admin-token", "")
        if not hmac.compare_digest(provided_token, lab_manager_token):
            raise HTTPException(status_code=401, detail="Lab Manager authentication required")

        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type == "model/gltf-binary":
            content = await _read_limited_request(request, _MAX_SCENE_BYTES, label="GLB")
            result = _store_scene(root, lab_id, content)
            result["contentType"] = "model/gltf-binary"
            return result
        if content_type == "application/zip":
            content = await _read_limited_request(request, _MAX_WEBAPP_ARCHIVE_BYTES, label="Three.js application")
            return _store_webapp(root, lab_id, content)
        raise HTTPException(status_code=415, detail="Content-Type must be model/gltf-binary or application/zip")

    @router.post("/admin/digital-twin-assets/{lab_id}/from-fmu")
    async def import_companion_asset(lab_id: str, request: Request):
        if not lab_id.isdigit() or len(lab_id) > 78:
            raise HTTPException(status_code=400, detail="Invalid laboratory ID")
        if not lab_manager_token:
            raise HTTPException(status_code=503, detail="Digital twin asset import is not configured")
        provided_token = request.headers.get("x-digital-twin-admin-token", "")
        if not hmac.compare_digest(provided_token, lab_manager_token):
            raise HTTPException(status_code=401, detail="Lab Manager authentication required")

        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="Content-Type must be application/json")
        try:
            request_body = await _read_limited_request(request, 4096, label="FMU scene import request")
            body = json.loads(request_body.decode("utf-8"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="A JSON accessKey is required") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="A JSON accessKey is required")
        access_key = _validate_access_key(body.get("accessKey"))
        asset_type = _validate_asset_type(body.get("assetType"))
        is_glb = asset_type == "glb"
        suffix = ".glb" if is_glb else ".webapp.zip"
        media_type = "model/gltf-binary" if is_glb else "application/zip"
        size_limit = _MAX_SCENE_BYTES if is_glb else _MAX_WEBAPP_ARCHIVE_BYTES

        if fmu_backend_mode == "local":
            if resolve_local_fmu_path is None:
                raise HTTPException(status_code=503, detail="Local FMU data is unavailable")
            try:
                fmu_path = Path(resolve_local_fmu_path(access_key)).resolve(strict=True)
                local_root = Path(fmu_data_root).expanduser().resolve(strict=True)
                fmu_path.relative_to(local_root)
                companion_path = fmu_path.with_name(fmu_path.stem + suffix).resolve(strict=True)
                companion_path.relative_to(local_root.resolve())
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="Companion digital twin asset not found for this FMU") from exc
            except (ValueError, IndexError) as exc:
                raise HTTPException(status_code=400, detail="Invalid companion GLB path") from exc
            try:
                if not companion_path.is_file():
                    raise HTTPException(status_code=404, detail="Companion digital twin asset not found for this FMU")
                if companion_path.stat().st_size > size_limit:
                    raise HTTPException(status_code=413, detail="Companion digital twin asset exceeds the size limit")
                content = companion_path.read_bytes()
            except OSError as exc:
                raise HTTPException(status_code=503, detail="Companion digital twin asset could not be read") from exc
            source = "gateway"
        elif fmu_backend_mode == "station":
            if not station_base_url or not station_internal_token:
                raise HTTPException(status_code=503, detail="Lab Station scene retrieval is not configured")
            station_url = urljoin(station_base_url.rstrip("/") + "/", "internal/fmu/companion-asset")
            headers = {
                "X-Internal-Session-Token": station_internal_token,
                "X-FMU-Access-Key": access_key,
            }
            try:
                async with httpx.AsyncClient(
                    timeout=station_request_timeout,
                    follow_redirects=False,
                ) as client:
                    async with client.stream("GET", station_url, params={"assetType": asset_type}, headers=headers) as response:
                        if response.status_code == 404:
                            raise HTTPException(status_code=404, detail="Companion digital twin asset not found on Lab Station")
                        if response.status_code != 200:
                            raise HTTPException(status_code=502, detail="Lab Station could not provide the companion digital twin asset")
                        response_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if response_type != media_type:
                            raise HTTPException(status_code=502, detail="Lab Station returned an invalid digital twin asset type")
                        content = await _read_limited_response(response, size_limit, asset_type)
            except HTTPException:
                raise
            except httpx.TimeoutException as exc:
                raise HTTPException(status_code=504, detail="Timed out retrieving companion digital twin asset from Lab Station") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="Could not retrieve companion digital twin asset from Lab Station") from exc
            source = "station"
        else:
            raise HTTPException(status_code=503, detail="Digital twin FMU backend mode is unsupported")

        stored = _store_scene(root, lab_id, content) if is_glb else _store_webapp(root, lab_id, content)
        stored["source"] = source
        stored["accessKey"] = access_key
        return stored

    return router
