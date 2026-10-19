import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile


def _parse_documentation_urls(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    try:
        parsed = json.loads(str(raw_value))
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return list(dict.fromkeys(
        str(item).strip()
        for item in parsed
        if str(item).strip()
    ))


def _validated_digital_twin_asset_url(raw_value: Any) -> str:
    """Accept a public GLB URL or this Gateway's managed visual asset path."""
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if len(value) > 2048 or "\\" in value or any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=400, detail="Invalid digital twin asset URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Accessing this validates malformed port values.
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid digital twin asset URL") from exc
    if parsed.scheme:
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not parsed.path.lower().endswith(".glb")
        ):
            raise HTTPException(status_code=400, detail="External digital twin assets must be HTTPS GLB files")
        return value
    segments = parsed.path.split("/")
    safe_glb = (
        len(segments) == 4
        and segments[1] == "digital-twin-scenes"
        and segments[2].isdigit()
        and re.fullmatch(r"[a-f0-9]{64}\.glb", segments[3], re.IGNORECASE) is not None
    )
    safe_app = (
        len(segments) == 5
        and segments[1] == "digital-twin-apps"
        and segments[2].isdigit()
        and re.fullmatch(r"[a-f0-9]{64}", segments[3], re.IGNORECASE) is not None
        and segments[4] == "index.html"
    )
    if not value.startswith("/") or value.startswith("//") or not (safe_glb or safe_app) or parsed.query or parsed.fragment:
        raise HTTPException(status_code=400, detail="Relative digital twin assets must reference an immutable Gateway GLB or app path")
    return value


def create_aas_sync_router(
    *,
    resolve_fmu_path: Any,
    read_model_description: Any,
    metadata_builder: Any,
    get_model_metadata: Any = None,
    sync_fmu_to_basyx: Any,
    logger: Any,
    get_runtime_status: Any = None,
    record_aasx: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/aas-admin/fmu/{access_key}/sync")
    async def aas_sync_fmu(access_key: str, request: Request):
        aasx_bytes: Optional[bytes] = None
        lab_id: Optional[str] = None
        aasx_filename: Optional[str] = None

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_lab_id = form.get("labId") or request.query_params.get("labId")
            if raw_lab_id:
                lab_id = str(raw_lab_id)
            upload = form.get("file") or form.get("aasx")
            if isinstance(upload, UploadFile):
                aasx_filename = upload.filename
                aasx_bytes = await upload.read()
            extra_info: dict = {}
            for field in ("description", "license", "documentationUrl", "contactEmail"):
                value = str(form.get(field) or request.query_params.get(field, "")).strip()
                if value:
                    extra_info[field] = value
            asset_url = _validated_digital_twin_asset_url(form.get("digitalTwinAssetUrl") or request.query_params.get("digitalTwinAssetUrl"))
            if asset_url:
                extra_info["digitalTwinAssetUrl"] = asset_url
            documentation_urls = _parse_documentation_urls(
                form.get("documentationUrls") or request.query_params.get("documentationUrls")
            )
            if documentation_urls:
                extra_info["documentationUrls"] = documentation_urls
        else:
            raw_lab_id = request.query_params.get("labId")
            if raw_lab_id:
                lab_id = raw_lab_id
            extra_info = {}
            for field in ("description", "license", "documentationUrl", "contactEmail"):
                value = request.query_params.get(field, "").strip()
                if value:
                    extra_info[field] = value
            asset_url = _validated_digital_twin_asset_url(request.query_params.get("digitalTwinAssetUrl"))
            if asset_url:
                extra_info["digitalTwinAssetUrl"] = asset_url
            documentation_urls = _parse_documentation_urls(request.query_params.get("documentationUrls"))
            if documentation_urls:
                extra_info["documentationUrls"] = documentation_urls

        metadata: dict = {}
        fmu_path: Optional[Path] = None
        if not aasx_bytes:
            if get_model_metadata is not None:
                try:
                    metadata = await get_model_metadata(access_key)
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.error(
                        "AAS sync: cannot read FMU metadata for %s: %s",
                        str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                        type(exc).__name__,
                    )
                    raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc
                if not isinstance(metadata, dict):
                    raise HTTPException(status_code=422, detail="FMU metadata response is invalid")
            else:
                fmu_path = resolve_fmu_path(access_key)
                try:
                    model_description = read_model_description(str(fmu_path))
                except Exception as exc:
                    logger.error(
                        "AAS sync: cannot read FMU %s: %s",
                        str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                        type(exc).__name__,
                    )
                    raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc
                metadata = metadata_builder(model_description)
            auto_fallback = {
                key: metadata.get(key, "")
                for key in ("description", "license")
                if metadata.get(key, "")
            }
            merged_extra_info = {**auto_fallback, **(extra_info or {})}
            merged_extra_info = {key: value for key, value in merged_extra_info.items() if value}
            runtime_info = None
            if get_runtime_status is not None:
                try:
                    runtime_info = await get_runtime_status(str(lab_id or access_key))
                except Exception as exc:
                    logger.warning(
                        "AAS sync: runtime status unavailable for lab %s: %s",
                        str(lab_id or access_key).replace("\r", "\\r").replace("\n", "\\n"),
                        type(exc).__name__,
                    )
        else:
            merged_extra_info = {key: value for key, value in (extra_info or {}).items() if value}
            runtime_info = None

        result = await sync_fmu_to_basyx(
            lab_id=lab_id or access_key,
            access_key=access_key,
            metadata=metadata,
            aasx_bytes=aasx_bytes,
            extra_info=merged_extra_info or None,
            fmu_path=fmu_path,
            unit_definitions=metadata.get("unitDefinitions", []),
            runtime_info=runtime_info,
        )
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        if aasx_bytes and lab_id and record_aasx and result.get("disabled") is not True:
            try:
                result["aasxPackage"] = record_aasx(
                    lab_id=lab_id,
                    filename=aasx_filename,
                    content=aasx_bytes,
                    sync_result=result,
                )
            except Exception as exc:
                logger.error("AASX association could not be recorded for lab %s: %s", lab_id, type(exc).__name__)
                raise HTTPException(status_code=500, detail="AASX association could not be recorded") from exc
        return result

    @router.post("/aas-admin/aas/{lab_id}/sync")
    async def aas_sync_resource_aasx(lab_id: str, request: Request):
        """Import a provider-prepared AASX package for any resource type."""
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            raise HTTPException(status_code=400, detail="AASX upload requires multipart/form-data")

        form = await request.form()
        upload = form.get("file") or form.get("aasx")
        if not isinstance(upload, UploadFile):
            raise HTTPException(status_code=400, detail="AASX file is required")
        aasx_bytes = await upload.read()
        if not aasx_bytes:
            raise HTTPException(status_code=400, detail="AASX file is empty")

        extra_info: dict = {}
        for field in ("description", "license", "documentationUrl", "contactEmail"):
            value = str(form.get(field) or request.query_params.get(field, "")).strip()
            if value:
                extra_info[field] = value
        asset_url = _validated_digital_twin_asset_url(form.get("digitalTwinAssetUrl") or request.query_params.get("digitalTwinAssetUrl"))
        if asset_url:
            extra_info["digitalTwinAssetUrl"] = asset_url
        documentation_urls = _parse_documentation_urls(form.get("documentationUrls"))
        if documentation_urls:
            extra_info["documentationUrls"] = documentation_urls

        result = await sync_fmu_to_basyx(
            lab_id=lab_id,
            access_key=lab_id,
            metadata={},
            aasx_bytes=aasx_bytes,
            extra_info=extra_info or None,
            fmu_path=None,
            unit_definitions=[],
            required_aas_id=f"urn:decentralabs:lab:{lab_id}",
        )
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        if record_aasx and result.get("disabled") is not True:
            try:
                result["aasxPackage"] = record_aasx(
                    lab_id=lab_id,
                    filename=upload.filename,
                    content=aasx_bytes,
                    sync_result=result,
                )
            except Exception as exc:
                logger.error("AASX association could not be recorded for lab %s: %s", lab_id, type(exc).__name__)
                raise HTTPException(status_code=500, detail="AASX association could not be recorded") from exc
        return result

    return router
