import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from aasx_limits import (
    AasxInvalidContentError,
    AasxLimitError,
    MAX_AASX_UPLOAD_BYTES,
)


async def _read_bounded_aasx_upload(upload: UploadFile) -> bytes:
    size = getattr(upload, "size", None)
    if isinstance(size, int) and size > MAX_AASX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"AASX upload exceeds the {MAX_AASX_UPLOAD_BYTES // (1024 * 1024)} MiB limit",
        )

    content = await upload.read(MAX_AASX_UPLOAD_BYTES + 1)
    if len(content) > MAX_AASX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"AASX upload exceeds the {MAX_AASX_UPLOAD_BYTES // (1024 * 1024)} MiB limit",
        )
    return content


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
    get_fmi_ls_related_resources: Any = None,
    sync_fmu_to_basyx: Any,
    logger: Any,
    get_runtime_status: Any = None,
    record_aasx: Any = None,
    invalidate_access_policy: Any = None,
    get_access_policy_status: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/aas-admin/fmu/{access_key}/sync")
    async def aas_sync_fmu(access_key: str, request: Request):
        aasx_bytes: Optional[bytes] = None
        lab_id: Optional[str] = None
        aasx_filename: Optional[str] = None
        raw_regenerate_access_policy: Any = request.query_params.get("regenerateAccessPolicy")

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_lab_id = form.get("labId") or request.query_params.get("labId")
            if raw_lab_id:
                lab_id = str(raw_lab_id)
            raw_regenerate_access_policy = form.get("regenerateAccessPolicy") or raw_regenerate_access_policy
            upload = form.get("file") or form.get("aasx")
            if isinstance(upload, UploadFile):
                aasx_filename = upload.filename
                aasx_bytes = await _read_bounded_aasx_upload(upload)
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

        if aasx_bytes and not lab_id:
            raise HTTPException(status_code=400, detail="FMU AASX import requires labId")

        regenerate_value = str(raw_regenerate_access_policy or "").strip().lower()
        if regenerate_value not in {"", "0", "1", "false", "true", "no", "yes"}:
            raise HTTPException(status_code=400, detail="regenerateAccessPolicy must be a boolean")
        force_regenerate_access_policy = regenerate_value in {"1", "true", "yes"}
        if aasx_bytes and force_regenerate_access_policy:
            raise HTTPException(
                status_code=400,
                detail="Remove the AASX upload before regenerating default access rules",
            )

        metadata: dict = {}
        fmu_path: Optional[Path] = None
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

        fmi_ls_resources = None
        if get_fmi_ls_related_resources is not None:
            try:
                candidate = await get_fmi_ls_related_resources(access_key)
                if isinstance(candidate, dict):
                    fmi_ls_resources = candidate
            except Exception as exc:
                # REF metadata is an optional public projection; preserve the
                # core AAS/FMU synchronization if an older Executor lacks it.
                logger.warning(
                    "AAS sync: FMI-LS-REF resources unavailable for %s: %s",
                    str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                    type(exc).__name__,
                )
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

        try:
            result = await sync_fmu_to_basyx(
                lab_id=lab_id or access_key,
                access_key=access_key,
                metadata=metadata,
                aasx_bytes=aasx_bytes,
                extra_info=merged_extra_info or None,
                fmi_ls_resources=fmi_ls_resources,
                fmu_path=fmu_path,
                unit_definitions=metadata.get("unitDefinitions", []),
                required_aas_id=f"urn:decentralabs:lab:{lab_id}" if aasx_bytes and lab_id else None,
                runtime_info=runtime_info,
                force_regenerate_access_policy=force_regenerate_access_policy,
            )
        except AasxLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except AasxInvalidContentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        if callable(invalidate_access_policy):
            invalidate_access_policy(lab_id or access_key)
        return result

    @router.get("/aas-admin/fmu/{access_key}/access-policy")
    async def inspect_fmu_access_policy(
        access_key: str,
        labId: str = Query(..., min_length=1, max_length=128),
    ):
        if get_access_policy_status is None:
            raise HTTPException(status_code=503, detail="FMU access policy status is unavailable")
        try:
            status = await get_access_policy_status(labId, access_key)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("FMU access policy status unavailable for lab %s: %s", labId, type(exc).__name__)
            raise HTTPException(status_code=503, detail="FMU access policy status is unavailable") from exc
        if not isinstance(status, dict):
            raise HTTPException(status_code=503, detail="FMU access policy status is unavailable")
        return JSONResponse(status, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

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
        aasx_bytes = await _read_bounded_aasx_upload(upload)
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

        try:
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
        except AasxLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except AasxInvalidContentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        if callable(invalidate_access_policy):
            invalidate_access_policy(lab_id)
        return result

    return router
