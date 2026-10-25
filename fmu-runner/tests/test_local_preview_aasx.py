import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from local_preview_aasx import LocalPreviewAasxRegistry


def _claims(access_key="demo/model.fmu"):
    import hashlib

    identity = hashlib.sha256(access_key.encode()).hexdigest()[:24]
    return {
        "sub": "local-preview",
        "labId": f"local_demo_{identity}",
        "reservationKey": f"local-preview-{identity}",
        "pucHash": f"local-preview-{identity}",
        "accessKey": access_key,
        "resourceType": "fmu",
    }


def test_registry_serializes_imports_records_and_links_one_aasx_per_fmu(tmp_path):
    claims = _claims()
    link_path = tmp_path / f"{claims['labId']}.aas-link.json"
    package_record = {}
    sync = AsyncMock(side_effect=[
        {"synced": True, "aasId": f"urn:decentralabs:lab:{claims['labId']}",
         "accessControlSubmodelId": f"urn:decentralabs:lab:{claims['labId']}:sm:simulationAccessControl"},
        {"synced": True, "accessPolicyPreserved": True,
         "accessControlSubmodelId": f"urn:decentralabs:lab:{claims['labId']}:sm:simulationAccessControl",
         "uploadedSubmodelIds": [f"urn:decentralabs:lab:{claims['labId']}:sm:simulationModels"]},
    ])
    policy = {"policySource": "aas-generated", "variables": {"input": {"writeAt": ["initialization"]}}}
    resolve_policy = AsyncMock(return_value=policy)
    serialize = AsyncMock(return_value={"content": b"PK\x03\x04aasx"})
    record = MagicMock(side_effect=lambda **kwargs: package_record.update(kwargs))
    shell = {
        "id": f"urn:decentralabs:lab:{claims['labId']}",
        "submodels": [{"keys": [{"value": f"urn:decentralabs:lab:{claims['labId']}:sm:simulationModels"}]}],
    }
    registry = LocalPreviewAasxRegistry(
        get_model_metadata=AsyncMock(return_value={"modelVariables": []}),
        sync_fmu_to_basyx=sync,
        serialize_aasx_resources=serialize,
        record_aasx=record,
        get_aasx_package=lambda _lab_id: package_record or None,
        get_link_path=lambda _lab_id: link_path,
        build_aas_shell=MagicMock(return_value=shell),
        get_effective_policy=resolve_policy,
        invalidate_access_policy=MagicMock(),
    )

    first = asyncio.run(registry.ensure(claims))
    second = asyncio.run(registry.ensure(claims))

    assert first["policySource"] == "aas-generated"
    assert second == first
    assert sync.await_count == 2
    assert sync.await_args_list[1].kwargs["aasx_bytes"] == b"PK\x03\x04aasx"
    assert record.call_args.kwargs["filename"] == f"{claims['labId']}.aasx"
    assert json.loads(link_path.read_text(encoding="utf-8"))["aasId"] == shell["id"]


def test_registry_refuses_a_missing_or_non_aas_policy(tmp_path):
    claims = _claims()
    link_path = tmp_path / f"{claims['labId']}.aas-link.json"
    link_path.write_text("{}", encoding="utf-8")
    registry = LocalPreviewAasxRegistry(
        get_model_metadata=AsyncMock(),
        sync_fmu_to_basyx=AsyncMock(),
        serialize_aasx_resources=AsyncMock(),
        record_aasx=MagicMock(),
        get_aasx_package=lambda _lab_id: {"labId": claims["labId"]},
        get_link_path=lambda _lab_id: link_path,
        build_aas_shell=MagicMock(),
        get_effective_policy=AsyncMock(return_value={"policySource": "fmi-default", "variables": {}}),
        invalidate_access_policy=MagicMock(),
    )

    try:
        asyncio.run(registry.ensure(claims))
    except RuntimeError as error:
        assert "AASX policy" in str(error)
    else:
        raise AssertionError("The registry must not silently accept the FMI fallback")
