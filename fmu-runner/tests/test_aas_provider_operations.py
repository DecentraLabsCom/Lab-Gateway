"""Provider updates stay inside one linked shell and publish only local visuals."""

from copy import deepcopy
import json

import httpx
import pytest

from aas_access_policy_resolver import AasAccessPolicyResolver
from aas_model_builders import build_simulation_access_control_submodel
import fmu_aas_generator as generator


class AasClient:
    def __init__(self, responses, update_status=204):
        self.responses = responses
        self.update_status = update_status
        self.writes = []
        self.reads = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, path):
        self.reads.append(path)
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value

    async def put(self, path, **kwargs):
        self.writes.append((path, deepcopy(kwargs)))
        return httpx.Response(self.update_status)


@pytest.fixture
def provider(tmp_path):
    metadata = {"fmiVersion": "3.0", "modelName": "Dual", "supportsCoSimulation": True,
                "supportsModelExchange": True, "modelVariables": [{"name": "u", "type": "Float64", "causality": "input"}]}
    submodel = build_simulation_access_control_submodel("42", metadata)
    shell = {"id": "urn:decentralabs:lab:42", "submodels": [{"keys": [{"type": "Submodel", "value": submodel["id"]}]}]}
    shell_path = "/shells/" + generator._encode_id(shell["id"])
    policy_path = "/submodels/" + generator._encode_id(submodel["id"])
    client = AasClient({shell_path: httpx.Response(200, json=shell), policy_path: httpx.Response(200, json=submodel)})
    resolver = AasAccessPolicyResolver(get_basyx_url=lambda: "http://basyx-mock",
        get_request_headers=lambda: {"Authorization": "Bearer provider-token"},
        get_link_path=lambda key: tmp_path / (key + ".json"), client_factory=lambda **_kwargs: client)
    return resolver, client, metadata, shell, submodel, shell_path, policy_path


@pytest.mark.asyncio
@pytest.mark.parametrize("property_exists", [False, True])
async def test_provider_can_add_or_replace_one_authorized_interface_property(provider, property_exists):
    resolver, client, metadata, _, submodel, _, path = provider
    elements = [p for p in submodel["submodelElements"] if p.get("idShort") != "AuthorizedExecutionInterfaces"]
    if property_exists:
        elements.append({"modelType": "Property", "idShort": "AuthorizedExecutionInterfaces", "value": '["CoSimulation"]'})
    submodel["submodelElements"] = elements
    client.responses[path] = httpx.Response(200, json=submodel)
    result = await resolver.update_authorized_execution_interfaces({"labId": "42"}, metadata, ["ModelExchange"])
    assert result == ["ModelExchange"]
    assert len(client.writes) == 1
    written_path, request = client.writes[0]
    assert written_path == path
    assert request["headers"]["Content-Type"] == "application/json"
    properties = [p for p in request["json"]["submodelElements"] if p.get("idShort") == "AuthorizedExecutionInterfaces"]
    assert len(properties) == 1
    assert properties[0]["valueType"] == "xs:string"
    assert json.loads(properties[0]["value"]) == ["ModelExchange"]
    assert request["json"]["id"] == submodel["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["shell-missing", "shell-id", "policy-missing", "policy-status", "policy-id",
                                     "wrong-property-kind", "duplicate-property", "nan", "oversize", "write-status", "network"])
async def test_provider_updates_fail_closed_for_wrong_resources_or_invalid_payloads(provider, failure):
    resolver, client, metadata, shell, submodel, shell_path, path = provider
    if failure == "shell-missing":
        client.responses[shell_path] = httpx.Response(404)
    elif failure == "shell-id":
        client.responses[shell_path] = httpx.Response(200, json={"id": "other"})
    elif failure == "policy-missing":
        client.responses[path] = httpx.Response(404)
    elif failure == "policy-status":
        client.responses[path] = httpx.Response(503)
    elif failure == "policy-id":
        client.responses[path] = httpx.Response(200, json={"id": "other"})
    elif failure in {"wrong-property-kind", "duplicate-property"}:
        submodel["submodelElements"] = [p for p in submodel["submodelElements"] if p.get("idShort") != "AuthorizedExecutionInterfaces"]
        prop = {"idShort": "AuthorizedExecutionInterfaces", "modelType": "Property", "value": "[]"}
        if failure == "wrong-property-kind":
            prop["modelType"] = "SubmodelElementCollection"
        submodel["submodelElements"].append(prop)
        if failure == "duplicate-property":
            submodel["submodelElements"].append(deepcopy(prop))
        client.responses[path] = httpx.Response(200, json=submodel)
    elif failure in {"nan", "oversize"}:
        submodel["providerExtension"] = float("nan") if failure == "nan" else "x" * (2 * 1_048_576)
        # AAS may return non-standard NaN; the update must never emit it again.
        client.responses[path] = httpx.Response(200, content=json.dumps(submodel).encode())
    elif failure == "write-status":
        client.update_status = 403
    elif failure == "network":
        client.responses[shell_path] = httpx.ConnectError("private upstream information")
    with pytest.raises(RuntimeError):
        await resolver.update_authorized_execution_interfaces({"labId": "42"}, metadata, ["CoSimulation"])
    assert len(client.writes) == (1 if failure == "write-status" else 0)


@pytest.mark.asyncio
async def test_interface_selection_requires_a_lab_and_multiple_executable_interfaces(provider):
    resolver, client, metadata, *_ = provider
    with pytest.raises(ValueError, match="laboratory"):
        await resolver.update_authorized_execution_interfaces({}, metadata, ["CoSimulation"])
    with pytest.raises(ValueError, match="multiple"):
        await resolver.update_authorized_execution_interfaces({"labId": "42"}, {**metadata, "supportsModelExchange": False}, ["CoSimulation"])
    assert not client.writes


def _handover(monkeypatch, elements):
    monkeypatch.setattr(generator, "BASYX_AAS_URL", generator._BUNDLED_AAS_URL)
    shell_id = "urn:decentralabs:lab:42"
    submodel_id = generator._submodel_id_for_handover("42")
    shell_path = "/shells/" + generator._encode_id(shell_id)
    path = "/submodels/" + generator._encode_id(submodel_id)
    client = AasClient({shell_path: httpx.Response(200, json={"id": shell_id, "submodelIds": [submodel_id]}),
                        path: httpx.Response(200, json={"id": submodel_id, "submodelElements": elements})})
    monkeypatch.setattr(generator.httpx, "AsyncClient", lambda **_kwargs: client)
    return client, shell_path, path


@pytest.mark.asyncio
async def test_handover_lists_only_same_lab_digest_bound_glb_and_webapp_files(monkeypatch):
    digest = "a" * 64
    elements = [None, {"modelType": "File", "value": 1},
        {"modelType": "File", "contentType": "text/html", "value": "https://outside.example/app.html"},
        {"modelType": "File", "contentType": "text/html", "value": f"/digital-twin-apps/other/{digest}/index.html"},
        {"modelType": "File", "idShort": "Scene", "contentType": "model/gltf-binary", "value": f"/digital-twin-scenes/42/{digest}.glb"},
        {"modelType": "SubmodelElementCollection", "value": [
            {"modelType": "File", "idShort": "App", "contentType": "TEXT/HTML; charset=utf-8", "value": f"/digital-twin-apps/42/{digest}/index.html"}]}]
    _, _, path = _handover(monkeypatch, elements)
    result = await generator.get_handover_visual_assets("42")
    assert [a["renderer"] for a in result] == ["glb", "threejs-app"]
    assert [a["elementIdShort"] for a in result] == ["Scene", "App"]
    assert all(a["submodelId"] == generator._submodel_id_for_handover("42") for a in result)
    assert result[1]["url"].endswith("/index.html")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["shell-404", "shell-status", "shell-id", "unlinked", "submodel-404", "submodel-status", "submodel-id", "network"])
async def test_handover_handles_absence_but_rejects_broken_aas_references(monkeypatch, failure):
    client, shell_path, path = _handover(monkeypatch, [])
    if failure == "shell-404":
        client.responses[shell_path] = httpx.Response(404)
    elif failure == "shell-status":
        client.responses[shell_path] = httpx.Response(503)
    elif failure == "shell-id":
        client.responses[shell_path] = httpx.Response(200, json={"id": "other"})
    elif failure == "unlinked":
        client.responses[shell_path] = httpx.Response(200, json={"id": "urn:decentralabs:lab:42", "submodels": []})
    elif failure == "submodel-404":
        client.responses[path] = httpx.Response(404)
    elif failure == "submodel-status":
        client.responses[path] = httpx.Response(503)
    elif failure == "submodel-id":
        client.responses[path] = httpx.Response(200, json={"id": "other"})
    else:
        client.responses[path] = httpx.ConnectError("private upstream information")
    if failure in {"shell-404", "submodel-404", "unlinked"}:
        assert await generator.get_handover_visual_assets("42") == []
    else:
        with pytest.raises(RuntimeError) as error:
            await generator.get_handover_visual_assets("42")
        assert "private upstream" not in str(error.value)
    assert client.reads[0] == shell_path
    if failure.startswith("submodel") or failure == "network":
        assert client.reads[-1] == path


@pytest.mark.asyncio
async def test_handover_enforces_result_count_and_depth_bounds(monkeypatch):
    scene = {"modelType": "File", "contentType": "model/gltf-binary", "value": "/digital-twin-scenes/42/" + "a" * 64 + ".glb"}
    _handover(monkeypatch, [deepcopy(scene) for _ in range(40)])
    assert len(await generator.get_handover_visual_assets("42")) == 32
    elements = [scene]
    for _ in range(14):
        elements = [{"modelType": "SubmodelElementCollection", "value": elements}]
    _handover(monkeypatch, elements)
    assert await generator.get_handover_visual_assets("42") == []
    assert await generator.get_handover_visual_assets("../other") == []
