import json
from pathlib import Path
from typing import Any, Optional

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


def create_aas_sync_router(
    *,
    resolve_fmu_path: Any,
    read_model_description: Any,
    metadata_builder: Any,
    sync_fmu_to_basyx: Any,
    logger: Any,
) -> APIRouter:
    router = APIRouter()

    @router.post("/aas-admin/fmu/{access_key}/sync")
    async def aas_sync_fmu(access_key: str, request: Request):
        aasx_bytes: Optional[bytes] = None
        lab_id: str = access_key

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_lab_id = form.get("labId") or request.query_params.get("labId")
            if raw_lab_id:
                lab_id = str(raw_lab_id)
            upload = form.get("file") or form.get("aasx")
            if isinstance(upload, UploadFile):
                aasx_bytes = await upload.read()
            extra_info: dict = {}
            for field in ("description", "license", "documentationUrl", "contactEmail"):
                value = str(form.get(field) or request.query_params.get(field, "")).strip()
                if value:
                    extra_info[field] = value
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
            documentation_urls = _parse_documentation_urls(request.query_params.get("documentationUrls"))
            if documentation_urls:
                extra_info["documentationUrls"] = documentation_urls

        metadata: dict = {}
        fmu_path: Optional[Path] = None
        if not aasx_bytes:
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
        else:
            merged_extra_info = {key: value for key, value in (extra_info or {}).items() if value}

        result = await sync_fmu_to_basyx(
            lab_id=lab_id,
            access_key=access_key,
            metadata=metadata,
            aasx_bytes=aasx_bytes,
            extra_info=merged_extra_info or None,
            fmu_path=fmu_path,
            unit_definitions=metadata.get("unitDefinitions", []),
        )
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return result

    return router
