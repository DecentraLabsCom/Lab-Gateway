from typing import Any

from fastapi import APIRouter, HTTPException


def create_aas_hints_router(
    *,
    resolve_fmu_path: Any,
    read_model_description: Any,
    normalize_xml_value: Any,
    logger: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/aas-admin/fmu/{access_key}/hints")
    async def aas_hints_fmu(access_key: str):
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