"""Provider-managed immutable storage for GLB scenes and Three.js applications."""

import hashlib
import hmac
import io
import json
import math
import os
import re
import struct
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin
import zipfile
from html.parser import HTMLParser

import httpx
from fastapi import APIRouter, HTTPException, Request

from fmi_ls_ref import read_visual_asset as read_fmi_ls_ref_visual_asset


_MAX_SCENE_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_ARCHIVE_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_ASSET_BYTES = 50 * 1024 * 1024
_MAX_WEBAPP_UNPACKED_BYTES = 120 * 1024 * 1024
_MAX_WEBAPP_FILES = 300
_EXECUTABLE_WEBAPP_EXTENSIONS = {
    ".app", ".bat", ".class", ".cmd", ".com", ".dll", ".dylib", ".exe",
    ".jar", ".msi", ".ps1", ".sh", ".so",
}
_GLB_HEADER = struct.Struct("<4sII")
_CHUNK_HEADER = struct.Struct("<II")
_GLB_MAGIC = b"glTF"
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_FMI_BINDING_TARGETS = {
    "position.x", "position.y", "position.z",
    "rotation.x", "rotation.y", "rotation.z",
    "scale.x", "scale.y", "scale.z",
    "visible", "material.color",
}
_FMI_INPUT_POSITION_TARGETS = {"position.x", "position.y", "position.z"}
_NUMERIC_FMI_INPUT_TYPES = {
    "real", "integer", "float32", "float64",
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
}


def _is_finite_binding_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_binding_color(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 0xFFFFFF
    return (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
        and 0 <= value <= 0xFFFFFF
    )


def _has_valid_fmi_binding_fields(binding: dict[str, Any]) -> bool:
    for field in ("scale", "offset", "visibleWhenGreaterThanOrEqual"):
        if field in binding and not _is_finite_binding_number(binding[field]):
            return False
    return all(
        field not in binding or _is_binding_color(binding[field])
        for field in ("trueColor", "falseColor")
    )


def _fmi_binding_scale(binding: dict[str, Any]) -> float:
    raw_scale = binding.get("scale", 1)
    return float(raw_scale) if _is_finite_binding_number(raw_scale) else math.nan


def _is_draggable_input_binding(binding: dict[str, Any], variable: dict[str, Any]) -> bool:
    return (
        _has_valid_fmi_binding_fields(binding)
        and str(variable.get("causality", "")).lower() == "input"
        and binding.get("target") in _FMI_INPUT_POSITION_TARGETS
        and str(variable.get("type", "")).lower() in _NUMERIC_FMI_INPUT_TYPES
        and math.isfinite(_fmi_binding_scale(binding))
        and _fmi_binding_scale(binding) != 0
    )


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

    if document is None:
        raise HTTPException(status_code=400, detail="GLB JSON chunk is missing")

    asset = document.get("asset")
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


def _validate_glb_bindings(document: dict[str, Any], model_metadata: Any) -> dict[str, Any]:
    model_variables = model_metadata.get("modelVariables") if isinstance(model_metadata, dict) else None
    if not isinstance(model_variables, list):
        return {
            "assetType": "glb",
            "status": "not_checked",
            "bindingCount": 0,
            "validBindingCount": 0,
            "issueCount": 0,
            "issues": [],
            "message": "FMU variable metadata was unavailable, so scene bindings could not be checked.",
        }

    variables_by_name: dict[str, dict[str, Any]] = {}
    for variable in model_variables:
        if not isinstance(variable, dict):
            continue
        variable_name = variable.get("name")
        if not isinstance(variable_name, str):
            continue
        variables_by_name[variable_name] = variable
    issues: list[dict[str, Any]] = []
    issue_count = 0
    binding_count = 0
    valid_binding_count = 0

    def add_issue(
        code: str,
        message: str,
        node_name: str,
        binding_index: int | None = None,
        variable: Any = None,
    ) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < 50:
            issue: dict[str, Any] = {
                "code": code,
                "message": message,
                "node": node_name[:120],
            }
            if binding_index is not None:
                issue["bindingIndex"] = binding_index
            if isinstance(variable, str):
                issue["variable"] = variable[:160]
            issues.append(issue)

    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        add_issue("invalid_nodes", "The GLB scene node list is invalid.", "Scene")
        nodes = []

    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        extras = node.get("extras")
        if not isinstance(extras, dict) or "fmiBindings" not in extras:
            continue
        raw_node_name = node.get("name")
        node_name = raw_node_name if isinstance(raw_node_name, str) else f"Node {node_index + 1}"
        bindings = extras.get("fmiBindings")
        if not isinstance(bindings, list):
            add_issue("invalid_binding_list", "fmiBindings must be an array.", node_name)
            continue

        target_counts: dict[str, int] = {}
        for candidate in bindings:
            candidate_target = candidate.get("target") if isinstance(candidate, dict) else None
            candidate_variable_name = candidate.get("variable") if isinstance(candidate, dict) else None
            candidate_variable = variables_by_name.get(candidate_variable_name) if isinstance(candidate_variable_name, str) else None
            candidate_has_valid_fields = (
                isinstance(candidate, dict) and _has_valid_fmi_binding_fields(candidate)
            )
            is_output_binding = (
                candidate_has_valid_fields
                and str(candidate_variable.get("causality", "")).lower() == "output"
                if candidate_variable
                else False
            )
            is_draggable_input = (
                _is_draggable_input_binding(candidate, candidate_variable)
                if isinstance(candidate, dict) and candidate_variable
                else False
            )
            if (
                isinstance(candidate_target, str)
                and candidate_target in _FMI_BINDING_TARGETS
                and (is_output_binding or is_draggable_input)
            ):
                target_counts[candidate_target] = target_counts.get(candidate_target, 0) + 1

        for binding_index, binding in enumerate(bindings):
            binding_count += 1
            if not isinstance(binding, dict):
                add_issue("invalid_binding", "The binding must be an object.", node_name, binding_index)
                continue

            variable_name = binding.get("variable")
            target = binding.get("target")
            valid = True
            for field in ("scale", "offset", "visibleWhenGreaterThanOrEqual"):
                if field in binding and not _is_finite_binding_number(binding[field]):
                    add_issue(
                        "invalid_binding_field",
                        f"The binding field '{field}' must be a finite JSON number.",
                        node_name,
                        binding_index,
                        variable_name,
                    )
                    valid = False
            for field in ("trueColor", "falseColor"):
                if field in binding and not _is_binding_color(binding[field]):
                    add_issue(
                        "invalid_binding_field",
                        f"The binding field '{field}' must be a non-empty color string or a 24-bit color integer.",
                        node_name,
                        binding_index,
                        variable_name,
                    )
                    valid = False
            if not isinstance(variable_name, str) or not variable_name:
                add_issue("missing_variable", "The binding must name an FMI input or output variable.", node_name, binding_index)
                valid = False
            elif variable_name not in variables_by_name:
                add_issue(
                    "unknown_variable",
                    "The variable is not declared by this FMU.",
                    node_name,
                    binding_index,
                    variable_name,
                )
                valid = False

            target_is_supported = isinstance(target, str) and target in _FMI_BINDING_TARGETS
            if not target_is_supported:
                add_issue(
                    "unsupported_target",
                    "The binding target is not supported by the Marketplace GLB viewer.",
                    node_name,
                    binding_index,
                    variable_name,
                )
                valid = False

            variable = variables_by_name.get(variable_name) if isinstance(variable_name, str) else None
            causality = str(variable.get("causality", "")).lower() if variable else ""
            if variable and causality not in {"input", "output"}:
                add_issue(
                    "unsupported_causality",
                    "GLB bindings can reference FMI inputs or outputs only.",
                    node_name,
                    binding_index,
                    variable_name,
                )
                valid = False
            elif variable and causality == "input" and target_is_supported:
                if target not in _FMI_INPUT_POSITION_TARGETS:
                    add_issue(
                        "unsupported_input_target",
                        "Writable scene inputs must target position.x, position.y, or position.z.",
                        node_name,
                        binding_index,
                        variable_name,
                    )
                    valid = False
                elif target_counts.get(target, 0) > 1:
                    add_issue(
                        "competing_input_target",
                        "This position target has another binding on the node, so the input cannot be dragged.",
                        node_name,
                        binding_index,
                        variable_name,
                    )
                    valid = False
                elif str(variable.get("type", "")).lower() not in _NUMERIC_FMI_INPUT_TYPES:
                    add_issue(
                        "non_numeric_input",
                        "A draggable scene input must be a numeric FMI variable.",
                        node_name,
                        binding_index,
                        variable_name,
                    )
                    valid = False
                elif not _has_valid_fmi_binding_fields(binding):
                    valid = False
                else:
                    scale = _fmi_binding_scale(binding)
                    if not math.isfinite(scale) or scale == 0:
                        add_issue(
                            "non_invertible_input_binding",
                            "An input position binding must have a finite, non-zero scale.",
                            node_name,
                            binding_index,
                            variable_name,
                        )
                        valid = False

            if valid:
                valid_binding_count += 1

    if binding_count == 0:
        add_issue("no_fmi_bindings", "This scene has no FMI bindings and will remain static.", "Scene")

    return {
        "assetType": "glb",
        "status": "passed" if issue_count == 0 else "warning",
        "bindingCount": binding_count,
        "validBindingCount": valid_binding_count,
        "issueCount": issue_count,
        "issues": issues,
        "message": "Scene bindings match this FMU's declared inputs and outputs." if issue_count == 0 else "Review the scene binding findings before publishing.",
    }


async def _asset_validation_report(
    asset_type: str,
    *,
    access_key: str,
    document: dict[str, Any] | None = None,
    get_model_metadata=None,
) -> dict[str, Any]:
    if asset_type == "threejs-app":
        return {
            "assetType": asset_type,
            "status": "passed",
            "message": "The application bundle structure is valid. Marketplace will confirm app startup when the viewer opens it.",
        }
    if not access_key or get_model_metadata is None or document is None:
        return {
            "assetType": "glb",
            "status": "not_checked",
            "bindingCount": 0,
            "validBindingCount": 0,
            "issueCount": 0,
            "issues": [],
            "message": "FMU variable metadata was unavailable, so scene bindings could not be checked.",
        }
    try:
        model_metadata = await get_model_metadata(access_key)
    except Exception:
        return {
            "assetType": "glb",
            "status": "not_checked",
            "bindingCount": 0,
            "validBindingCount": 0,
            "issueCount": 0,
            "issues": [],
            "message": "FMU variable metadata could not be read, so scene bindings were not checked.",
        }
    return _validate_glb_bindings(document, model_metadata)


class _WebappAssetReferenceParser(HTMLParser):
    """Reject remote asset loads while allowing ordinary HTTPS documentation links."""

    _NAVIGATION_TAGS = frozenset({"a", "area"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_unbundled_asset = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in {"src", "href"} or not value:
                continue
            reference = value.strip()
            navigation_link = name == "href" and tag.lower() in self._NAVIGATION_TAGS
            if navigation_link and reference.lower().startswith("https://"):
                continue
            if re.match(r"(?:https?:)?//|/", reference, re.IGNORECASE):
                self.has_unbundled_asset = True


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
                if path.suffix.lower() in _EXECUTABLE_WEBAPP_EXTENSIONS:
                    raise HTTPException(status_code=400, detail="Application archive must not contain executable files")
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
    references = _WebappAssetReferenceParser()
    references.feed(html)
    if references.has_unbundled_asset:
        raise HTTPException(
            status_code=400,
            detail="Three.js application must bundle remote assets; HTTPS navigation links are allowed",
        )
    if len(files) > _MAX_WEBAPP_FILES:
        raise HTTPException(status_code=413, detail="Three.js application has too many files")
    return files


def _store_scene(
    root: Path,
    lab_id: str,
    content: bytes,
    *,
    validated_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if validated_document is None:
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
    if normalized not in {"auto", "glb", "threejs-app"}:
        raise HTTPException(status_code=400, detail="assetType must be auto, glb, or threejs-app")
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


def store_local_preview_assets(
    *,
    root: Path,
    lab_id: str,
    access_key: str,
    fmu_data_root: Path,
    resolve_local_fmu_path,
) -> list[dict[str, str]]:
    """Store local companion visuals under their synthetic preview lab ID.

    This helper is only used by the local-preview provisioner. The public
    Lab Manager routes continue to accept numeric lab IDs exclusively.
    """
    if not isinstance(lab_id, str) or re.fullmatch(r"local_demo_[a-f0-9]{24}", lab_id) is None:
        raise ValueError("Invalid local preview laboratory ID")
    access_key = _validate_access_key(access_key)
    expected_lab_id = f"local_demo_{hashlib.sha256(access_key.encode()).hexdigest()[:24]}"
    if lab_id != expected_lab_id:
        raise ValueError("Local preview laboratory ID does not match its FMU")
    if resolve_local_fmu_path is None:
        return []

    try:
        local_root = Path(fmu_data_root).expanduser().resolve(strict=True)
        fmu_path = Path(resolve_local_fmu_path(access_key)).resolve(strict=True)
        fmu_path.relative_to(local_root)
    except FileNotFoundError:
        return []
    except (ValueError, IndexError) as exc:
        raise ValueError("Invalid local preview companion asset path") from exc

    asset_root = Path(root).expanduser().resolve()
    assets: list[dict[str, str]] = []
    for suffix, asset_type in ((".webapp.zip", "threejs-app"), (".glb", "glb")):
        try:
            companion_path = fmu_path.with_name(fmu_path.stem + suffix).resolve(strict=True)
            companion_path.relative_to(local_root)
        except (FileNotFoundError, ValueError):
            continue

        content = _read_local_companion(companion_path, asset_type)
        if content is None:
            continue
        if asset_type == "glb":
            document = _validate_glb(content)
            stored = _store_scene(asset_root, lab_id, content, validated_document=document)
            content_type = "model/gltf-binary"
            renderer = "glb"
        else:
            stored = _store_webapp(asset_root, lab_id, content)
            content_type = "text/html"
            renderer = "threejs-app"
        assets.append({
            "path": stored["path"],
            "contentType": content_type,
            "renderer": renderer,
        })
    return assets


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


def _read_local_companion(path: Path, asset_type: str) -> bytes | None:
    if not path.is_file():
        return None
    size_limit = _MAX_SCENE_BYTES if asset_type == "glb" else _MAX_WEBAPP_ARCHIVE_BYTES
    label = "GLB" if asset_type == "glb" else "Three.js application"
    try:
        if path.stat().st_size > size_limit:
            raise HTTPException(status_code=413, detail=f"Companion {label} exceeds the size limit")
        content = path.read_bytes()
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Companion {label} could not be read") from exc
    if len(content) > size_limit:
        raise HTTPException(status_code=413, detail=f"Companion {label} exceeds the size limit")
    return content


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
    get_model_metadata=None,
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
            access_key = request.headers.get("x-fmu-access-key", "").strip()
            if access_key:
                access_key = _validate_access_key(access_key)
            document = _validate_glb(content)
            result = _store_scene(root, lab_id, content, validated_document=document)
            result["contentType"] = "model/gltf-binary"
            result["validation"] = await _asset_validation_report(
                "glb",
                access_key=access_key,
                document=document,
                get_model_metadata=get_model_metadata,
            )
            return result
        if content_type == "application/zip":
            content = await _read_limited_request(request, _MAX_WEBAPP_ARCHIVE_BYTES, label="Three.js application")
            result = _store_webapp(root, lab_id, content)
            result["validation"] = await _asset_validation_report("threejs-app", access_key="")
            return result
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
        selected_asset_type = asset_type
        asset_source = "legacy-sibling"
        content = None

        if fmu_backend_mode == "local":
            if resolve_local_fmu_path is None:
                raise HTTPException(status_code=503, detail="Local FMU data is unavailable")
            try:
                fmu_path = Path(resolve_local_fmu_path(access_key)).resolve(strict=True)
                local_root = Path(fmu_data_root).expanduser().resolve(strict=True)
                fmu_path.relative_to(local_root)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="FMU was not found") from exc
            except (ValueError, IndexError) as exc:
                raise HTTPException(status_code=400, detail="Invalid companion asset path") from exc

            if asset_type == "auto":
                declared_asset = read_fmi_ls_ref_visual_asset(fmu_path)
                if declared_asset is not None and declared_asset[1] == "threejs-app":
                    content, selected_asset_type, asset_source = declared_asset
                else:
                    app_path = fmu_path.with_name(fmu_path.stem + ".webapp.zip")
                    try:
                        app_path = app_path.resolve(strict=True)
                        app_path.relative_to(local_root)
                    except (FileNotFoundError, ValueError):
                        app_path = None
                    if app_path is not None:
                        content = _read_local_companion(app_path, "threejs-app")
                        selected_asset_type = "threejs-app"
                        asset_source = "legacy-sibling"
                    elif declared_asset is not None:
                        content, selected_asset_type, asset_source = declared_asset
                    else:
                        glb_path = fmu_path.with_name(fmu_path.stem + ".glb")
                        try:
                            glb_path = glb_path.resolve(strict=True)
                            glb_path.relative_to(local_root)
                        except (FileNotFoundError, ValueError):
                            glb_path = None
                        if glb_path is not None:
                            content = _read_local_companion(glb_path, "glb")
                            selected_asset_type = "glb"
            else:
                suffix = ".glb" if asset_type == "glb" else ".webapp.zip"
                try:
                    companion_path = fmu_path.with_name(fmu_path.stem + suffix).resolve(strict=True)
                    companion_path.relative_to(local_root)
                except (FileNotFoundError, ValueError) as exc:
                    raise HTTPException(status_code=404, detail="Companion digital twin asset not found for this FMU") from exc
                content = _read_local_companion(companion_path, asset_type)
                if content is None:
                    raise HTTPException(status_code=404, detail="Companion digital twin asset not found for this FMU")
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
                    async def read_station_asset(requested_type: str):
                        async with client.stream(
                            "GET", station_url, params={"assetType": requested_type}, headers=headers,
                        ) as response:
                            if response.status_code == 404:
                                return None
                            if response.status_code == 400 and requested_type == "auto":
                                try:
                                    error_body = json.loads((await response.aread()).decode("utf-8"))
                                except (UnicodeDecodeError, json.JSONDecodeError):
                                    error_body = {}
                                if error_body.get("detail") == "INVALID_COMPANION_ASSET_TYPE":
                                    return "auto-unsupported"
                            if response.status_code != 200:
                                raise HTTPException(status_code=502, detail="Lab Station could not provide the companion digital twin asset")

                            resolved_type = requested_type
                            resolved_source = "legacy-sibling"
                            if requested_type == "auto":
                                resolved_type = response.headers.get("x-digital-twin-asset-type", "").strip().lower()
                                if resolved_type not in {"glb", "threejs-app"}:
                                    raise HTTPException(status_code=502, detail="Lab Station returned an invalid digital twin asset type")
                                resolved_source = response.headers.get("x-digital-twin-asset-source", "").strip().lower()
                                if resolved_source not in {"fmi-ls-ref", "legacy-sibling"}:
                                    raise HTTPException(status_code=502, detail="Lab Station returned an invalid digital twin asset source")
                            response_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                            expected_media_type = "model/gltf-binary" if resolved_type == "glb" else "application/zip"
                            if response_type != expected_media_type:
                                raise HTTPException(status_code=502, detail="Lab Station returned an invalid digital twin asset type")
                            size_limit = _MAX_SCENE_BYTES if resolved_type == "glb" else _MAX_WEBAPP_ARCHIVE_BYTES
                            response_content = await _read_limited_response(response, size_limit, resolved_type)
                            return response_content, resolved_type, resolved_source

                    station_asset = await read_station_asset(asset_type)
                    if station_asset == "auto-unsupported":
                        # Older Station Executors do not accept `auto`; preserve their
                        # same-name companion behavior until the REF-aware release lands.
                        for fallback_type in ("threejs-app", "glb"):
                            station_asset = await read_station_asset(fallback_type)
                            if station_asset is not None:
                                break
                    if station_asset is None or station_asset == "auto-unsupported":
                        raise HTTPException(status_code=404, detail="Companion digital twin asset not found on Lab Station")
                    content, selected_asset_type, asset_source = station_asset
            except HTTPException:
                raise
            except httpx.TimeoutException as exc:
                raise HTTPException(status_code=504, detail="Timed out retrieving companion digital twin asset from Lab Station") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="Could not retrieve companion digital twin asset from Lab Station") from exc
            source = "station"
        else:
            raise HTTPException(status_code=503, detail="Digital twin FMU backend mode is unsupported")

        if content is None:
            raise HTTPException(status_code=404, detail="Companion digital twin asset not found for this FMU")

        is_glb = selected_asset_type == "glb"
        document = _validate_glb(content) if is_glb else None
        stored = (
            _store_scene(root, lab_id, content, validated_document=document)
            if is_glb
            else _store_webapp(root, lab_id, content)
        )
        stored["source"] = source
        stored["assetSource"] = asset_source
        stored["assetType"] = selected_asset_type
        stored["accessKey"] = access_key
        stored["validation"] = await _asset_validation_report(
            selected_asset_type,
            access_key=access_key,
            document=document,
            get_model_metadata=get_model_metadata,
        )
        return stored

    return router
