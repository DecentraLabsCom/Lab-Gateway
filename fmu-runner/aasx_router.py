"""HTTP routes for the Lab Manager AAS association catalog."""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


def create_aasx_router(*, association_service: Any, serialize_resources: Any) -> APIRouter:
    router = APIRouter()

    async def association_or_404(lab_id: str) -> dict:
        association = await association_service.get_association(lab_id)
        if association is None:
            raise HTTPException(status_code=404, detail="AAS association not found")
        return association

    @router.get("/aas-admin/aas/catalog")
    async def list_aas_associations():
        result = await association_service.list_associations()
        if not isinstance(result, dict):
            raise HTTPException(status_code=502, detail="AAS association discovery failed")
        return result

    @router.get("/aas-admin/aas/{lab_id}/view")
    async def view_aas_association(lab_id: str):
        """Return the association metadata and current BaSyx resource IDs."""
        return await association_or_404(lab_id)

    @router.get("/aas-admin/aas/{lab_id}/download")
    async def download_aas_association(lab_id: str):
        association = await association_or_404(lab_id)
        serialization = await serialize_resources(
            shell_ids=association.get("shellIds") or [],
            submodel_ids=association.get("submodelIds") or [],
        )
        if not isinstance(serialization, dict) or serialization.get("error"):
            if isinstance(serialization, dict) and serialization.get("disabled"):
                raise HTTPException(status_code=503, detail="BaSyx serialization is unavailable")
            raise HTTPException(status_code=502, detail="AASX package could not be generated from BaSyx")
        content = serialization.get("content")
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise HTTPException(status_code=502, detail="BaSyx returned an empty AASX package")
        media_type = str(
            serialization.get("mediaType")
            or "application/asset-administration-shell-package+xml"
        )
        return Response(
            content=bytes(content),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{association.get("filename") or f"{lab_id}.aasx"}"',
                "Cache-Control": "no-store",
            },
        )

    @router.delete("/aas-admin/aas/{lab_id}")
    async def delete_aas_association(lab_id: str):
        deletion = await association_service.delete_association(lab_id)
        if deletion is None:
            raise HTTPException(status_code=404, detail="AAS association not found")
        if deletion.get("error"):
            if deletion.get("disabled"):
                raise HTTPException(status_code=503, detail="BaSyx deletion is unavailable")
            raise HTTPException(status_code=502, detail="AAS resources could not be deleted")
        return deletion

    return router


__all__ = ["create_aasx_router"]
