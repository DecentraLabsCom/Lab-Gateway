"""Local integration probe: linked Part 4 AASX policy -> Gateway -> FMU Executor.

Run this script in a container attached to the local Gateway AAS network. It
imports a temporary provider AASX into the configured BaSyx instance, creates
the normal Gateway AAS link, checks a denied write, performs one real FMU run,
and removes the temporary AAS resources and link when finished.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import secrets
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fmu_aas_generator as aas
from aas_access_policy_resolver import AasAccessPolicyResolver
from aas_link_router import create_aas_link_router
from fmu_backend import StationFmuBackend
from run_router import create_run_router


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required integration setting is missing: {name}")
    return value


def _write_test_aasx(lab_id: str, access_key: str, metadata: dict[str, Any]) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    simulation_model = aas.build_simulation_submodel(lab_id, access_key, metadata)
    access_control = aas.build_simulation_access_control_submodel(
        lab_id,
        metadata,
        simulation_model_submodel_id=simulation_model["id"],
    )
    shell = aas.build_aas_shell(
        lab_id,
        access_key,
        metadata,
        extra_submodel_ids=[access_control["id"]],
    )

    rule_document = {
        "AllAccessPermissionRules": {
            "DEFATTRIBUTES": [{
                "name": "reservationLab",
                "attributes": [{"CLAIM": "labId"}],
            }],
            "DEFACLS": [
                {
                    "name": "readOutputs",
                    "acl": {
                        "USEATTRIBUTES": "reservationLab",
                        "RIGHTS": ["READ"],
                        "ACCESS": "ALLOW",
                    },
                },
                {
                    "name": "writeTorque",
                    "acl": {
                        "USEATTRIBUTES": "reservationLab",
                        "RIGHTS": ["UPDATE"],
                        "ACCESS": "ALLOW",
                    },
                },
            ],
            "DEFOBJECTS": [
                {
                    "name": "visibleMotorSpeed",
                    "objects": [{
                        "REFERABLE": (
                            f'$sme({json.dumps(simulation_model["id"])}).'
                            "SimulationModel.Ports.Output.out_motor_speed"
                        ),
                    }],
                },
                {
                    "name": "torqueInput",
                    "objects": [{
                        "REFERABLE": (
                            f'$sme({json.dumps(simulation_model["id"])}).'
                            "SimulationModel.Ports.Input.in_torque"
                        ),
                    }],
                },
            ],
            "DEFFORMULAS": [{
                "name": "sameLab",
                "formula": {"$eq": [
                    {"$attribute": {"CLAIM": "labId"}},
                    {"$strVal": lab_id},
                ]},
            }],
            "rules": [
                {
                    "USEACL": "readOutputs",
                    "USEOBJECTS": ["visibleMotorSpeed"],
                    "USEFORMULA": "sameLab",
                },
                {
                    "USEACL": "writeTorque",
                    "USEOBJECTS": ["torqueInput"],
                    "USEFORMULA": "sameLab",
                },
            ],
        },
    }
    encoded_rules = json.dumps(
        rule_document,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    rules_blob = next(
        item for item in access_control["submodelElements"]
        if item.get("idShort") == "AllAccessPermissionRules"
    )
    rules_blob["value"] = base64.b64encode(encoded_rules).decode("ascii")

    environment = {
        "assetAdministrationShells": [shell],
        "submodels": [simulation_model, access_control],
        "conceptDescriptions": [],
    }
    buffer = io.BytesIO()
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin"'
        ' Target="/aasx/data.json" Id="r1"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("_rels/.rels", relationships)
        package.writestr("aasx/data.json", json.dumps(environment, ensure_ascii=False))
    return buffer.getvalue(), shell, simulation_model, access_control


async def _describe_fmu(executor_url: str, access_key: str, token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=executor_url, timeout=30.0) as client:
        response = await client.get(
            "/internal/fmu/describe",
            headers={
                "X-Internal-Session-Token": token,
                "X-FMU-Access-Key": access_key,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(f"FMU Executor metadata request failed with HTTP {response.status_code}")
    metadata = response.json()
    if not isinstance(metadata, dict) or not isinstance(metadata.get("modelVariables"), list):
        raise RuntimeError("FMU Executor returned invalid model metadata")
    return metadata


async def _import_aasx(package: bytes, lab_id: str, access_key: str, metadata: dict[str, Any]) -> dict[str, Any]:
    result = await aas.sync_fmu_to_basyx(
        lab_id=lab_id,
        access_key=access_key,
        metadata=metadata,
        aasx_bytes=package,
        required_aas_id=f"urn:decentralabs:lab:{lab_id}",
    )
    if result.get("error") or result.get("disabled") or result.get("accessPolicyPreserved") is not True:
        raise RuntimeError("BaSyx did not preserve the temporary AASX access policy")
    return result


def main() -> None:
    access_key = _required_environment("FMU_ACCESS_KEY")
    executor_url = _required_environment("FMU_LOCAL_EXECUTOR_BASE_URL")
    token_file = Path(_required_environment("FMU_LOCAL_EXECUTOR_INTERNAL_TOKEN_FILE"))
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("FMU Executor internal token file is empty")

    lab_id = f"policy-e2e-{secrets.token_hex(6)}"
    reservation_key = secrets.token_hex(16)
    claims = {
        "accessKey": access_key,
        "labId": lab_id,
        "reservationKey": reservation_key,
        "pucHash": secrets.token_hex(32),
        "resourceType": "fmu",
        "exp": int(time.time()) + 1800,
    }
    shell_id = f"urn:decentralabs:lab:{lab_id}"
    simulation_model_id = f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"
    access_control_id = f"urn:decentralabs:lab:{lab_id}:sm:simulationAccessControl"
    uploaded = False

    try:
        metadata = asyncio.run(_describe_fmu(executor_url, access_key, token))
        variable_names = {
            item.get("name")
            for item in metadata["modelVariables"]
            if isinstance(item, dict)
        }
        if not {"in_torque", "add.k1", "out_motor_speed", "out_load_speed"}.issubset(variable_names):
            raise RuntimeError("The selected FMU does not match the DC motor access-policy probe")

        package, shell, simulation_model, access_control = _write_test_aasx(lab_id, access_key, metadata)
        simulation_model_id = simulation_model["id"]
        access_control_id = access_control["id"]
        shell_id = shell["id"]
        uploaded = True
        asyncio.run(_import_aasx(package, lab_id, access_key, metadata))

        with tempfile.TemporaryDirectory(prefix="aas-policy-e2e-") as temp_dir:
            link_root = Path(temp_dir)

            def link_path(key: str) -> Path:
                encoded_key = base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii").rstrip("=")
                return link_root / f"{encoded_key}.aas-link.json"

            link_app = FastAPI()
            link_app.include_router(create_aas_link_router(get_link_path=link_path))
            with TestClient(link_app) as link_client:
                linked = link_client.post(
                    f"/aas-admin/lab/{lab_id}/aas-link",
                    json={
                        "aasId": shell_id,
                        "labId": lab_id,
                        "submodelIds": [simulation_model_id, access_control_id],
                        "accessControlSubmodelId": access_control_id,
                    },
                )
                if linked.status_code != 200 or linked.json().get("linked") is not True:
                    raise RuntimeError("The temporary AAS link could not be created")

                resolver = AasAccessPolicyResolver(
                    get_basyx_url=lambda: aas.BASYX_AAS_URL,
                    get_request_headers=aas._aas_request_headers,
                    get_link_path=link_path,
                    cache_ttl_seconds=0,
                )
                policy = asyncio.run(resolver.resolve(claims, metadata))
                if policy.get("policySource") != "aas-provider":
                    raise RuntimeError("The Gateway resolver did not load the imported provider policy")
                if policy["variables"]["in_torque"]["writeAt"] != ["initialization", "runtime"]:
                    raise RuntimeError("The imported AASX policy did not grant the declared torque write")
                if policy["variables"]["out_load_speed"]["read"] is not False:
                    raise RuntimeError("The imported AASX policy exposed an output that should be private")

                backend = StationFmuBackend(base_url=executor_url, internal_token=token, request_timeout=120.0)
                counted_backend = _CountingBackend(backend)

                async def verify_jwt():
                    return claims

                async def get_effective_policy(request_claims):
                    return await resolver.resolve(request_claims, metadata)

                async def no_op(*_args, **_kwargs):
                    return None

                run_app = FastAPI()
                run_app.include_router(create_run_router(
                    verify_jwt=verify_jwt,
                    enforce_fmu_claim=lambda _claims: None,
                    get_station_backend=lambda: counted_backend,
                    simulation_request_payload=lambda request, simulation_id: {
                        **request.model_dump(),
                        "simId": simulation_id,
                    },
                    extract_authorization_header=lambda _request: None,
                    record_browser_session_started=no_op,
                    new_simulation_id=lambda: f"gateway-e2e-{secrets.token_hex(8)}",
                    get_effective_policy=get_effective_policy,
                ))
                with TestClient(run_app) as run_client:
                    denied = run_client.post(
                        "/api/v1/simulations/run",
                        json={
                            "labId": lab_id,
                            "reservationKey": reservation_key,
                            "parameters": {"add.k1": 1.0},
                        },
                    )
                    if denied.status_code != 403 or counted_backend.run_count != 0:
                        raise RuntimeError("The Gateway forwarded a write denied by the linked AAS policy")

                    allowed = run_client.post(
                        "/api/v1/simulations/run",
                        json={
                            "labId": lab_id,
                            "reservationKey": reservation_key,
                            "parameters": {"in_torque": 0.0},
                            "options": {"startTime": 0.0, "stopTime": 0.1, "stepSize": 0.01},
                        },
                    )
                    if allowed.status_code != 200 or counted_backend.run_count != 1:
                        raise RuntimeError("The permitted FMU simulation did not reach the Executor")
                    result_payload = allowed.json()
                    expected_outputs = {"out_motor_speed"}
                    visible_outputs = result_payload.get("outputs")
                    if not isinstance(visible_outputs, dict) or set(visible_outputs) != expected_outputs:
                        raise RuntimeError("The Gateway response did not filter FMU outputs by the AAS policy")
                    if "out_load_speed" in json.dumps(result_payload, ensure_ascii=False):
                        raise RuntimeError("A private FMU output name leaked into the Gateway response")

                unlink = link_client.delete(f"/aas-admin/lab/{lab_id}/aas-link")
                if unlink.status_code != 200:
                    raise RuntimeError("The temporary AAS link could not be removed")

        print(json.dumps({
            "aasxImport": "passed",
            "part4ReusableDefinitions": "passed",
            "gatewayDeniedWriteStatus": 403,
            "executorSimulation": "passed",
            "visibleOutputs": ["out_motor_speed"],
            "temporaryAasx": "removed",
        }))
    finally:
        if uploaded:
            cleanup = asyncio.run(aas.delete_aasx_resources(
                shell_ids=[shell_id],
                submodel_ids=[simulation_model_id, access_control_id],
            ))
            if cleanup.get("error"):
                raise RuntimeError("Temporary AASX resources could not be removed from BaSyx")


class _CountingBackend:
    def __init__(self, backend: StationFmuBackend):
        self.backend = backend
        self.run_count = 0

    def build_authorized_context(self, **kwargs):
        return self.backend.build_authorized_context(**kwargs)

    async def run_authorized_simulation(self, **kwargs):
        self.run_count += 1
        return await self.backend.run_authorized_simulation(**kwargs)


if __name__ == "__main__":
    main()
