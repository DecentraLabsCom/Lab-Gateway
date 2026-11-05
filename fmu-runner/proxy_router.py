"""HTTP composition for reservation-scoped FMU proxy downloads.

The router owns only request sequencing and response construction.  Security,
ticket issuance, backend access, and artifact generation are injected so the
application composition root keeps control of deployment-specific behavior.
"""

from typing import Any, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from catalog_router import filter_authorized_experiments, filter_authorized_parameter_sets
from proxy_artifact import ProxyFmiLsRefSizeLimitError
from simulation_access_policy import filter_model_description


def _model_exchange_local_variable_references(metadata: Mapping[str, Any]) -> tuple[set[int], set[str]]:
    """Find local variables required by the authorized FMI ME description."""
    references: set[int] = set()
    names: set[str] = set()

    def add_reference(value: Any) -> None:
        if type(value) is int and value >= 0:
            references.add(value)

    def add_structure(raw_structure: Any) -> None:
        if not isinstance(raw_structure, Mapping):
            return
        for entries in raw_structure.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                for field in ("valueReference", "stateValueReference"):
                    add_reference(entry.get(field))
                for field in ("name", "stateName"):
                    name = entry.get(field)
                    if isinstance(name, str) and name:
                        names.add(name)
                dependencies = entry.get("dependencies")
                if isinstance(dependencies, list):
                    for dependency in dependencies:
                        add_reference(dependency)
                dependency_names = entry.get("dependencyNames")
                if isinstance(dependency_names, list):
                    names.update(name for name in dependency_names if isinstance(name, str) and name)

    add_structure(metadata.get("modelStructure"))
    # FMI 3 dimensions may refer to a local UInt64 constant or structural
    # parameter by value reference. Keep those variables in the proxy
    # description so array dimensions remain resolvable after filtering.
    model_variables = metadata.get("modelVariables")
    if isinstance(model_variables, list):
        for variable in model_variables:
            if not isinstance(variable, Mapping):
                continue
            dimensions = variable.get("dimensions")
            if not isinstance(dimensions, list):
                continue
            for dimension in dimensions:
                if not isinstance(dimension, Mapping):
                    continue
                add_reference(dimension.get("valueReference"))
                dimension_name = dimension.get("variableName") or dimension.get("name")
                if isinstance(dimension_name, str) and dimension_name:
                    names.add(dimension_name)

    fmi_ls_dae = metadata.get("fmiLsDae")
    if isinstance(fmi_ls_dae, Mapping):
        raw_algebraic_names = fmi_ls_dae.get("algebraicVariables")
        if isinstance(raw_algebraic_names, list):
            names.update(name for name in raw_algebraic_names if isinstance(name, str) and name)
        raw_algebraic_references = fmi_ls_dae.get("algebraicValueReferences")
        if isinstance(raw_algebraic_references, list):
            for reference in raw_algebraic_references:
                add_reference(reference)
        raw_residuals = fmi_ls_dae.get("residualVariables")
        if isinstance(raw_residuals, list):
            for residual in raw_residuals:
                if not isinstance(residual, Mapping):
                    continue
                add_reference(residual.get("valueReference"))
                name = residual.get("name")
                if isinstance(name, str) and name:
                    names.add(name)
        add_structure(fmi_ls_dae.get("modelStructure"))

    return references, names


def create_proxy_router(
    *,
    verify_jwt: Any,
    enforce_fmu_claim: Any,
    get_claim_lab_id: Any,
    enforce_requested_reservation: Any,
    allow_proxy_download: Any,
    extract_authorization_header: Any,
    new_request_id: Any,
    issue_session_ticket: Any,
    derive_gateway_ws_url: Any,
    get_authorized_model_metadata: Any,
    get_effective_policy: Any = None,
    get_effective_policy_for_metadata: Any = None,
    get_authorized_parameter_sets: Any = None,
    get_authorized_experiments: Any = None,
    build_proxy_model_description_xml: Any,
    parse_fmi_major_version: Any,
    proxy_model_identifier: Any,
    collect_runtime_files: Any,
    build_proxy_session_config: Any,
    build_proxy_artifact: Any,
    build_proxy_artifact_headers: Any,
    normalize_ticket_id: Any,
    get_signing_key: Any,
    logger: Any,
) -> APIRouter:
    router = APIRouter()

    async def authorized_connection(
        lab_id: str,
        request: Request,
        reservationKey: Optional[str] = Query(None),
        claims: dict = Depends(verify_jwt),
    ):
        """Shared authorization and one-use ticket for browser and native clients."""
        enforce_fmu_claim(claims)

        claim_lab_id = get_claim_lab_id(claims)
        if claim_lab_id and str(claim_lab_id) != str(lab_id):
            raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")

        claim_reservation_key = str(claims.get("reservationKey") or "").strip()
        enforce_requested_reservation(claims, reservationKey)
        effective_reservation_key = reservationKey or claim_reservation_key
        if not effective_reservation_key:
            raise HTTPException(status_code=400, detail="Missing reservationKey")

        claim_sub = str(claims.get("sub") or "anonymous")
        rate_key = f"{claim_sub}:{lab_id}"
        if not allow_proxy_download(rate_key):
            raise HTTPException(status_code=429, detail="Proxy download rate limit exceeded. Retry shortly.")

        authorization = extract_authorization_header(request)
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing bearer token required to issue session ticket")

        fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
        if not fmu_filename:
            raise HTTPException(status_code=400, detail="Cannot determine FMU file name from token")

        session_ticket, ticket_expiry = await issue_session_ticket(
            authorization,
            lab_id=str(lab_id),
            reservation_key=effective_reservation_key,
            request_id=new_request_id(),
        )
        gateway_ws_url = derive_gateway_ws_url(claims)
        return claims, {
            "protocolVersion": "1.0", "gatewayWsUrl": gateway_ws_url,
            "labId": str(lab_id), "reservationKey": effective_reservation_key,
            "sessionTicket": session_ticket, "ticketExpiresAt": ticket_expiry,
        }

    @router.post("/api/v1/fmu/connection/{lab_id}")
    async def browser_connection(connection=Depends(authorized_connection)):
        """Give an authorized browser client the same capability as proxy.fmu."""
        from fastapi.responses import JSONResponse
        _, config = connection
        return JSONResponse(config, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    @router.get("/api/v1/fmu/proxy/{lab_id}")
    async def download_proxy_fmu(connection=Depends(authorized_connection)):
        """Generate and download a reservation-scoped FMU proxy artifact."""
        claims, connection_config = connection
        lab_id = connection_config["labId"]
        effective_reservation_key = connection_config["reservationKey"]
        session_ticket = connection_config["sessionTicket"]
        ticket_expiry = connection_config["ticketExpiresAt"]
        gateway_ws_url = connection_config["gatewayWsUrl"]
        fmu_filename = claims.get("accessKey") or claims.get("fmuFileName")
        model_metadata = await get_authorized_model_metadata(
            claims=claims,
            requested_fmu_filename=str(fmu_filename),
            include_internal_variables=True,
        )
        access_policy = None
        if get_effective_policy_for_metadata is not None:
            access_policy = await get_effective_policy_for_metadata(claims, model_metadata)
        elif get_effective_policy is not None:
            access_policy = await get_effective_policy(claims)
        if access_policy is not None:
            if not isinstance(access_policy, dict) or not isinstance(access_policy.get("variables"), dict):
                raise HTTPException(status_code=503, detail="FMU access policy is unavailable")
            authorized_interfaces = access_policy.get("authorizedExecutionInterfaces")
            if not isinstance(authorized_interfaces, list) or not authorized_interfaces:
                raise HTTPException(status_code=503, detail="Authorized FMI execution interfaces are unavailable")
        else:
            available_interfaces = model_metadata.get("availableExecutionInterfaces")
            if not isinstance(available_interfaces, list) or not available_interfaces:
                available_interfaces = ["CoSimulation"] if model_metadata.get("supportsCoSimulation") else ["ModelExchange"]
            authorized_interfaces = (
                ["CoSimulation"] if "CoSimulation" in available_interfaces else list(available_interfaces)
            )

        # Co-Simulation proxies expose external ports. Model Exchange also
        # needs the local variables referenced by its ModelStructure (states,
        # derivatives, event indicators and their declared dependencies).
        # Keep those structural variables while excluding unrelated local
        # implementation details from the downloaded FMI interface.
        required_local_references, required_local_names = _model_exchange_local_variable_references(model_metadata)
        model_variables = []
        for variable in model_metadata.get("modelVariables", []):
            if not isinstance(variable, dict):
                continue
            causality = str(variable.get("causality") or "local").lower()
            if causality != "local":
                model_variables.append(variable)
                continue
            reference = variable.get("valueReference")
            name = variable.get("name")
            if (
                "ModelExchange" in authorized_interfaces
                and (
                    (type(reference) is int and reference in required_local_references)
                    or (isinstance(name, str) and name in required_local_names)
                )
            ):
                model_variables.append(variable)
        model_metadata = {**model_metadata, "modelVariables": model_variables}

        if access_policy is not None:
            model_metadata = filter_model_description(
                access_policy,
                model_metadata,
                include_proxy_dae_selector=True,
                include_proxy_model_exchange="ModelExchange" in authorized_interfaces,
            )
            model_metadata["authorizedExecutionInterfaces"] = list(authorized_interfaces)
        else:
            model_metadata["authorizedExecutionInterfaces"] = list(authorized_interfaces)
        raw_parameter_sets = (
            await get_authorized_parameter_sets(claims=claims)
            if get_authorized_parameter_sets is not None
            else []
        )
        raw_experiments = (
            await get_authorized_experiments(claims=claims)
            if get_authorized_experiments is not None
            else {"resourceSets": [], "truncated": False}
        )
        fmi_ls_parameter_sets = (
            filter_authorized_parameter_sets(raw_parameter_sets, access_policy)
            if access_policy is not None
            else []
        )
        fmi_ls_experiments = (
            filter_authorized_experiments(raw_experiments, access_policy)
            if access_policy is not None
            else []
        )
        model_xml = build_proxy_model_description_xml(model_metadata)
        proxy_fmi_version = (
            "3.0" if parse_fmi_major_version(model_metadata.get("fmiVersion")) >= 3 else "2.0.3"
        )
        proxy_model_identifier_value = proxy_model_identifier(model_metadata)
        runtime_files = collect_runtime_files(
            fmi_version=proxy_fmi_version,
            model_identifier=proxy_model_identifier_value,
        )

        config_payload = build_proxy_session_config(
            fmi_version=proxy_fmi_version,
            gateway_ws_url=gateway_ws_url,
            lab_id=str(lab_id),
            reservation_key=effective_reservation_key,
            session_ticket=session_ticket,
            ticket_expires_at=ticket_expiry,
        )
        try:
            archive_bytes = build_proxy_artifact(
                model_xml=model_xml,
                config_payload=config_payload,
                runtime_files=runtime_files,
                fmi_ls_struct=model_metadata.get("fmiLsStruct"),
                fmi_ls_dae=(
                    model_metadata.get("fmiLsDae")
                    if "ModelExchange" in model_metadata.get("authorizedExecutionInterfaces", [])
                    else None
                ),
                fmi_ls_parameter_sets=fmi_ls_parameter_sets,
                fmi_ls_experiments=fmi_ls_experiments,
                fmi_ls_model_metadata=model_metadata,
            )
        except ProxyFmiLsRefSizeLimitError as error:
            raise HTTPException(
                status_code=413,
                detail="FMI-LS-REF resources exceed the supported proxy FMU size limit",
            ) from error
        signing_key = get_signing_key()
        headers = build_proxy_artifact_headers(
            artifact_bytes=archive_bytes,
            lab_id=str(lab_id),
            signing_key=signing_key,
        )

        logger.info(
            "Generated proxy FMU lab_id=%s reservation_key=%s ticket_id=%s bytes=%s sha256=%s signed=%s",
            str(lab_id).replace("\r", "\\r").replace("\n", "\\n"),
            str(effective_reservation_key).replace("\r", "\\r").replace("\n", "\\n"),
            str(normalize_ticket_id(session_ticket) or "-").replace("\r", "\\r").replace("\n", "\\n"),
            len(archive_bytes),
            headers["X-Proxy-Artifact-Sha256"],
            "yes" if signing_key else "no",
        )
        return Response(content=archive_bytes, media_type="application/octet-stream", headers=headers)

    return router
