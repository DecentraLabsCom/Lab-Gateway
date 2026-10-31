import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from fmu_state_capabilities import normalize_fmu_state_capabilities
from simulation_access_policy import filter_model_description


def create_catalog_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_authorized_model_metadata: Any,
    get_authorized_parameter_sets: Any = None,
    get_authorized_experiments: Any = None,
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
            {
                "modelVariables": policy.get("modelVariables", []),
                "fmiLsStruct": policy.get("fmiLsStruct"),
            },
        )
        response = {
            "policySource": policy.get("policySource", "unavailable"),
            "policyVersion": policy.get("policyVersion", ""),
            "variables": visible,
            "modelVariables": [
                variable for variable in visible_metadata.get("modelVariables", [])
                if isinstance(variable, dict)
            ],
        }
        model_description = policy.get("modelDescription")
        if isinstance(model_description, dict):
            for field in ("fmiVersion", "simulationType"):
                value = model_description.get(field)
                if isinstance(value, str) and value.strip() and len(value) <= 32:
                    response[field] = value.strip()
            # The Executor's current session runtime captures/restores state
            # through its Co-Simulation path. Do not offer the UI controls for
            # a Model Exchange-only FMU even if its XML declares the generic
            # state serialization flags.
            state_capabilities = normalize_fmu_state_capabilities(model_description)
            if state_capabilities is not None:
                response["fmuState"] = state_capabilities
        if get_authorized_experiments is not None:
            raw_experiments = await get_authorized_experiments(claims=claims)
            response["fmiLsExperiments"] = filter_authorized_experiments(raw_experiments, policy)
        if isinstance(visible_metadata.get("fmiLsStruct"), dict):
            response["fmiLsStruct"] = visible_metadata["fmiLsStruct"]
        return response

    @router.get("/api/v1/simulations/parameter-sets")
    async def fmi_ls_parameter_sets(claims: dict = Depends(verify_jwt)):
        """Return complete FMI-LS-REF parameter presets allowed by this reservation."""
        enforce_fmu_claim(claims)
        if get_authorized_parameter_sets is None or get_effective_policy is None:
            return {"fmiLsParameterPresets": []}

        raw_presets = await get_authorized_parameter_sets(claims=claims)
        policy = await get_effective_policy(claims)
        if (
            not isinstance(policy, dict)
            or not isinstance(policy.get("variables"), dict)
            or not isinstance(policy.get("modelVariables"), list)
            or not isinstance(raw_presets, list)
        ):
            raise HTTPException(status_code=503, detail="FMU parameter access policy is unavailable")

        return {"fmiLsParameterPresets": filter_authorized_parameter_sets(raw_presets, policy)}

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


def filter_authorized_parameter_sets(raw_presets: Any, policy: Any) -> list[dict[str, Any]]:
    """Keep only complete initialization presets permitted by a variable policy."""
    if (
        not isinstance(policy, dict)
        or not isinstance(policy.get("variables"), dict)
        or not isinstance(policy.get("modelVariables"), list)
        or not isinstance(raw_presets, list)
    ):
        return []

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
    return safe_presets


def filter_authorized_experiments(raw_discovery: Any, policy: Any) -> list[dict[str, Any]]:
    """Keep usable REF experiments whose initialization and runtime writes are authorized."""
    if (
        not isinstance(raw_discovery, dict)
        or not isinstance(raw_discovery.get("resourceSets"), list)
        or not isinstance(policy, dict)
        or not isinstance(policy.get("variables"), dict)
        or not isinstance(policy.get("modelVariables"), list)
    ):
        return []

    safe_experiments: list[dict[str, Any]] = []
    model_variables = {
        variable.get("name"): variable
        for variable in policy["modelVariables"]
        if isinstance(variable, dict) and isinstance(variable.get("name"), str)
    }
    runtime_names = {
        name for name, permission in policy["variables"].items()
        if isinstance(permission, dict)
        and isinstance(permission.get("writeAt"), list)
        and "runtime" in permission["writeAt"]
        and isinstance(model_variables.get(name), dict)
        and (
            str(model_variables[name].get("causality") or "").lower() == "input"
            or (
                str(model_variables[name].get("causality") or "").lower() == "parameter"
                and str(model_variables[name].get("variability") or "").lower() == "tunable"
            )
        )
    }
    for set_index, resource_set in enumerate(raw_discovery["resourceSets"][:8]):
        if not isinstance(resource_set, dict) or not isinstance(resource_set.get("experiments"), list):
            continue
        set_description = resource_set.get("description")
        for experiment_index, experiment in enumerate(resource_set["experiments"][:16]):
            if (
                not isinstance(experiment, dict)
                or experiment.get("status") != "ready"
                or experiment.get("eligibleForSmokeProbe") is False
            ):
                continue
            name = experiment.get("name")
            parameters = experiment.get("parameters")
            parameter_units = experiment.get("parameterUnits", {})
            options = experiment.get("options", {})
            raw_schedule = experiment.get("inputSchedule", [])
            if (
                not isinstance(name, str)
                or not name.strip()
                or len(name) > 180
                or not isinstance(parameters, dict)
                or len(parameters) > 2048
                or not isinstance(parameter_units, dict)
                or not isinstance(options, dict)
                or not isinstance(raw_schedule, list)
                or len(raw_schedule) > 128
            ):
                continue

            safe_options: dict[str, float] = {}
            valid_options = True
            for option_name, value in options.items():
                if (
                    option_name not in {"startTime", "stopTime", "stepSize"}
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or (option_name == "stepSize" and value <= 0)
                ):
                    valid_options = False
                    break
                safe_options[option_name] = float(value)
            if not valid_options:
                continue
            if (
                "startTime" in safe_options
                and "stopTime" in safe_options
                and safe_options["stopTime"] <= safe_options["startTime"]
            ):
                continue

            if parameters:
                safe_parameter_sets = filter_authorized_parameter_sets(
                    [{
                        "id": "experiment-parameters",
                        "name": name,
                        "description": "",
                        "parameters": parameters,
                        "parameterUnits": parameter_units,
                    }],
                    policy,
                )
                if not safe_parameter_sets:
                    continue
                safe_parameters = safe_parameter_sets[0]["parameters"]
            else:
                if parameter_units:
                    continue
                safe_parameters = {}

            safe_schedule: list[dict[str, Any]] = []
            if raw_schedule:
                start = safe_options.get("startTime")
                stop = safe_options.get("stopTime")
                step = safe_options.get("stepSize")
                if (
                    start is None or stop is None or step is None
                    or not math.isfinite(start) or not math.isfinite(stop) or not math.isfinite(step)
                    or step <= 0 or stop <= start
                ):
                    continue
                schedule_valid = True
                previous_time = start
                seen_values: set[tuple[float, str]] = set()
                for event in raw_schedule:
                    if not isinstance(event, dict) or set(event) != {"time", "values"}:
                        schedule_valid = False
                        break
                    event_time = event["time"]
                    values = event["values"]
                    if (
                        isinstance(event_time, bool) or not isinstance(event_time, (int, float))
                        or not math.isfinite(event_time) or event_time < start or event_time >= stop
                        or event_time < previous_time or not isinstance(values, dict) or not values
                    ):
                        schedule_valid = False
                        break
                    step_index = round((event_time - start) / step)
                    tolerance = max(1e-9, abs(step) * 1e-7)
                    if abs(start + step_index * step - event_time) > tolerance:
                        schedule_valid = False
                        break
                    safe_values: dict[str, float] = {}
                    for variable_name, value in values.items():
                        identity = (float(event_time), variable_name)
                        if (
                            not isinstance(variable_name, str) or not variable_name
                            or len(variable_name) > 512 or variable_name not in runtime_names
                            or isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(value) or identity in seen_values
                        ):
                            schedule_valid = False
                            break
                        safe_values[variable_name] = float(value)
                        seen_values.add(identity)
                    if not schedule_valid:
                        break
                    safe_schedule.append({"time": float(event_time), "values": safe_values})
                    previous_time = float(event_time)
                if not schedule_valid:
                    continue

            if not safe_parameters and not safe_options and not safe_schedule:
                continue
            description = experiment.get("description")
            if not isinstance(description, str) or not description.strip():
                description = set_description if isinstance(set_description, str) else ""
            safe_experiments.append({
                "id": f"experiment-{set_index}-{experiment_index}",
                "name": name.strip(),
                "description": description[:2048],
                "parameters": safe_parameters,
                "options": safe_options,
                **({"inputSchedule": safe_schedule} if safe_schedule else {}),
            })
    return safe_experiments
