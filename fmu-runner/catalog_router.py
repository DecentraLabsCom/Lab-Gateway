from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from simulation_access_policy import filter_model_description


def create_catalog_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_authorized_model_metadata: Any,
    get_authorized_parameter_sets: Any = None,
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

    @router.get("/api/v1/simulations/parameter-sets")
    async def provider_parameter_sets(claims: dict = Depends(verify_jwt)):
        """Return only complete provider presets the reservation may apply."""
        enforce_fmu_claim(claims)
        if get_authorized_parameter_sets is None or get_effective_policy is None:
            return {"presets": []}

        raw_presets = await get_authorized_parameter_sets(claims=claims)
        policy = await get_effective_policy(claims)
        if (
            not isinstance(policy, dict)
            or not isinstance(policy.get("variables"), dict)
            or not isinstance(policy.get("modelVariables"), list)
            or not isinstance(raw_presets, list)
        ):
            raise HTTPException(status_code=503, detail="FMU parameter access policy is unavailable")

        variables = {
            variable.get("name"): variable
            for variable in policy["modelVariables"]
            if isinstance(variable, dict) and isinstance(variable.get("name"), str)
        }
        safe_presets = []
        for preset in raw_presets[:24]:
            if not isinstance(preset, dict):
                continue
            preset_id = preset.get("id")
            name = preset.get("name")
            values = preset.get("parameters")
            parameter_units = preset.get("parameterUnits", {})
            if (
                not isinstance(preset_id, str)
                or len(preset_id) > 64
                or not isinstance(name, str)
                or not name.strip()
                or len(name) > 180
                or not isinstance(values, dict)
                or not isinstance(parameter_units, dict)
                or not values
                or len(values) > 2048
            ):
                continue

            filtered_values: dict[str, Any] = {}
            complete = True
            for variable_name, value in values.items():
                permission = policy["variables"].get(variable_name)
                variable = variables.get(variable_name)
                write_at = permission.get("writeAt") if isinstance(permission, dict) else None
                if (
                    not isinstance(variable_name, str)
                    or len(variable_name) > 512
                    or not isinstance(write_at, list)
                    or "initialization" not in write_at
                    or variable is None
                    or not (
                        str(variable.get("causality") or "").lower() == "input"
                        or (
                            str(variable.get("causality") or "").lower() == "parameter"
                            and str(variable.get("variability") or "").lower() != "constant"
                        )
                    )
                ):
                    complete = False
                    break

                source_unit = parameter_units.get(variable_name)
                if source_unit is not None and (
                    not isinstance(source_unit, str)
                    or source_unit != variable.get("unit")
                ):
                    complete = False
                    break

                if str(variable.get("type") or "").lower() == "enumeration":
                    enum_items = variable.get("enumItems")
                    if not isinstance(enum_items, list):
                        complete = False
                        break
                    enum_values = {
                        item.get("name"): item.get("value")
                        for item in enum_items
                        if isinstance(item, dict)
                        and isinstance(item.get("name"), str)
                        and isinstance(item.get("value"), (int, float))
                        and not isinstance(item.get("value"), bool)
                    }
                    raw_enum_values = value if isinstance(value, list) else [value]
                    if any(item not in enum_values for item in raw_enum_values):
                        complete = False
                        break
                    value = [enum_values[item] for item in raw_enum_values] if isinstance(value, list) else enum_values[value]

                if not _is_safe_parameter_value(value):
                    complete = False
                    break
                filtered_values[variable_name] = value

            # Keeping the set intact avoids silently changing a provider's
            # intended configuration when some of its variables are hidden.
            if not complete or not filtered_values:
                continue
            description = preset.get("description")
            safe_presets.append({
                "id": preset_id,
                "name": name.strip(),
                "description": description[:1024] if isinstance(description, str) else "",
                "parameters": filtered_values,
            })

        return {"presets": safe_presets}

    @router.get("/api/v1/fmu/list")
    async def list_fmus(claims: dict = Depends(verify_jwt)):
        enforce_fmu_claim(claims)
        return await list_authorized_fmu(claims=claims)

    return router


def _is_safe_parameter_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return len(value) <= 65536
    if isinstance(value, int):
        return -(2**53 - 1) <= value <= 2**53 - 1
    if isinstance(value, float):
        return value == value and abs(value) != float("inf")
    if isinstance(value, list):
        return len(value) <= 4096 and all(
            not isinstance(item, (dict, list)) and _is_safe_parameter_value(item)
            for item in value
        )
    return False
