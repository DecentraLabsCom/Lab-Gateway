from typing import Any

from fastapi import APIRouter, HTTPException


def create_aas_hints_router(
    *,
    resolve_fmu_path: Any,
    read_model_description: Any,
    normalize_xml_value: Any,
    logger: Any,
    get_model_metadata: Any = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/aas-admin/fmu/{access_key}/hints")
    async def aas_hints_fmu(access_key: str):
        if get_model_metadata is not None:
            try:
                metadata = await get_model_metadata(access_key)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(
                    "Cannot read FMU metadata for %s",
                    str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                    type(exc).__name__,
                )
                raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc
            if not isinstance(metadata, dict):
                raise HTTPException(status_code=422, detail="FMU metadata response is invalid")
            return {
                field: value
                for field, value in (
                    ("description", metadata.get("description")),
                    ("license", metadata.get("license")),
                    ("author", metadata.get("author")),
                    ("version", metadata.get("version")),
                    ("generationTool", metadata.get("generationTool")),
                )
                if isinstance(value, str) and value.strip()
            }

        fmu_path = resolve_fmu_path(access_key)
        try:
            model_description = read_model_description(fmu_path)
        except Exception as exc:
            logger.error(
                "Cannot read FMU model description for %s",
                str(access_key).replace("\r", "\\r").replace("\n", "\\n"),
                type(exc).__name__,
            )
            raise HTTPException(status_code=422, detail="Cannot read FMU model description") from exc

        hints: dict = {}
        for field_name, attribute_name in (
            ("description", "description"),
            ("license", "license"),
            ("author", "author"),
            ("version", "version"),
            ("generationTool", "generationTool"),
        ):
            value = normalize_xml_value(getattr(model_description, attribute_name, None))
            if value:
                hints[field_name] = value
        return hints

    return router
