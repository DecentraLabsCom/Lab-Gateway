from typing import Any

from fastapi import APIRouter, Depends, Query


def create_catalog_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_authorized_model_metadata: Any,
    public_model_metadata: Any,
    list_authorized_fmu: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/simulations/describe")
    async def describe(
        fmuFileName: str = Query(..., description="Name of the .fmu file"),
        claims: dict = Depends(verify_jwt),
    ):
        enforce_fmu_claim(claims, allow_provider_describe=True)
        metadata = await get_authorized_model_metadata(
            claims=claims,
            requested_fmu_filename=fmuFileName,
        )
        return public_model_metadata(metadata)

    @router.get("/api/v1/fmu/list")
    async def list_fmus(claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        return await list_authorized_fmu(claims=claims)

    return router