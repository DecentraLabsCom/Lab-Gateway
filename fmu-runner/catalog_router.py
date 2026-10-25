from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from simulation_access_policy import filter_model_description


def create_catalog_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_authorized_model_metadata: Any,
    public_model_metadata: Any,
    list_authorized_fmu: Any,
    get_effective_policy: Any = None,
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
            include_internal_variables=False,
        )
        public = public_model_metadata(metadata)
        # Provider-describe tokens are issued during AAS synchronization and
        # do not represent a reservation-bound consumer session.
        if (
            get_effective_policy is None
            or not all(str(claims.get(name) or "").strip() for name in ("labId", "reservationKey", "pucHash"))
        ):
            return public
        policy = await get_effective_policy(claims)
        if not isinstance(policy, dict) or not isinstance(policy.get("variables"), dict):
            raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
        public = filter_model_description(policy, public)
        return public

    @router.get("/api/v1/simulations/access")
    async def effective_variable_access(claims: dict = Depends(verify_jwt)):
        """Return the reservation's effective variable capabilities for its UI."""
        enforce_fmu_claim(claims)
        if get_effective_policy is None:
            return {"policySource": "fmi-default", "policyVersion": "", "variables": {}}
        policy = await get_effective_policy(claims)
        if not isinstance(policy, dict) or not isinstance(policy.get("variables"), dict):
            raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
        visible = {
            name: permission
            for name, permission in policy["variables"].items()
            if isinstance(name, str)
            and isinstance(permission, dict)
            and (permission.get("read") is True or bool(permission.get("writeAt")))
        }
        visible_metadata = filter_model_description(
            policy,
            {"modelVariables": policy.get("modelVariables", [])},
        )
        return {
            "policySource": policy.get("policySource", "unavailable"),
            "policyVersion": policy.get("policyVersion", ""),
            "variables": visible,
            "modelVariables": [
                variable for variable in visible_metadata.get("modelVariables", [])
                if isinstance(variable, dict)
            ],
        }

    @router.get("/api/v1/fmu/list")
    async def list_fmus(claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        return await list_authorized_fmu(claims=claims)

    return router
