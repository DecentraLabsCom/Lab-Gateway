"""HTTP routes for the Lab Manager AASX package catalog."""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


def create_aasx_router(*, catalog: Any, serialize_resources: Any, delete_resources: Any) -> APIRouter:
    router = APIRouter()

    def package_or_404(lab_id: str) -> dict:
        try:
            package = catalog.get(lab_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="AASX package not found") from error
        if package is None:
            raise HTTPException(status_code=404, detail="AASX package not found")
        return package

    @router.get("/aas-admin/aas/catalog")
    async def list_aasx_packages():
        return {"packages": catalog.list_packages()}

    @router.get("/aas-admin/aas/{lab_id}/view")
    async def view_aasx_package(lab_id: str):
        """Return the catalog metadata and imported resource IDs."""
        return package_or_404(lab_id)

    @router.get("/aas-admin/aas/{lab_id}/download")
    async def download_aasx_package(lab_id: str):
        package = package_or_404(lab_id)
        serialization = await serialize_resources(
            shell_ids=package.get("shellIds") or [],
            submodel_ids=package.get("submodelIds") or [],
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
                "Content-Disposition": f'attachment; filename="{package["filename"]}"',
                "Cache-Control": "no-store",
            },
        )

    @router.delete("/aas-admin/aas/{lab_id}")
    async def delete_aasx_package(lab_id: str):
        package = package_or_404(lab_id)
        deletion = await delete_resources(
            shell_ids=package.get("shellIds") or [],
            submodel_ids=package.get("submodelIds") or [],
        )
        if not isinstance(deletion, dict) or deletion.get("error"):
            if isinstance(deletion, dict) and deletion.get("disabled"):
                raise HTTPException(status_code=503, detail="BaSyx deletion is unavailable")
            raise HTTPException(status_code=502, detail="AASX resources could not be deleted from BaSyx")
        try:
            deleted = catalog.delete(lab_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="AASX package not found") from error
        if not deleted:
            raise HTTPException(status_code=404, detail="AASX package not found")
        return {
            "deleted": True,
            "labId": str(lab_id).strip(),
            "deletedAasIds": deletion.get("deletedAasIds", []),
            "deletedSubmodelIds": deletion.get("deletedSubmodelIds", []),
        }

    return router


__all__ = ["create_aasx_router"]
