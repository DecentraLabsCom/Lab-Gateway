import base64
import json

import pytest

from aas_access_policy_resolver import AasAccessPolicyResolver
from fmu_aas_generator import (
    _aas_id_for_lab,
    _encode_id,
    _submodel_id_for_access_control,
    build_simulation_access_control_submodel,
)
from simulation_access_policy import build_part4_access_rules


@pytest.fixture
def metadata():
    return {
        "modelVariables": [
            {"name": "command", "causality": "input", "variability": "continuous", "type": "Real", "valueReference": 1},
            {"name": "speed", "causality": "output", "variability": "continuous", "type": "Real", "valueReference": 2},
        ],
    }


class Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class Client:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, path):
        self.calls.append(path)
        return self.responses[path]


def make_resolver(tmp_path, monkeypatch, responses):
    import fmu_aas_generator

    monkeypatch.setattr(fmu_aas_generator, "BASYX_AAS_URL", "http://basyx-aas-server:8081")
    client = Client(responses)
    return AasAccessPolicyResolver(
        get_basyx_url=lambda: fmu_aas_generator.BASYX_AAS_URL,
        get_request_headers=lambda: {},
        get_link_path=lambda key: tmp_path / f"{key}.aas-link.json",
        client_factory=lambda **_kwargs: client,
    ), client


@pytest.mark.asyncio
async def test_resolves_generated_policy_from_linked_shell_submodel(tmp_path, monkeypatch, metadata):
    lab_id = "42"
    shell_id = _aas_id_for_lab(lab_id)
    policy_id = _submodel_id_for_access_control(lab_id)
    shell = {
        "id": shell_id,
        "submodels": [
            {"keys": [{"type": "Submodel", "value": policy_id}]},
            {"keys": [{"type": "Submodel", "value": f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"}]},
        ],
    }
    submodel = build_simulation_access_control_submodel(lab_id, metadata)
    resolver, client = make_resolver(tmp_path, monkeypatch, {
        f"/shells/{_encode_id(shell_id)}": Response(200, shell),
        f"/submodels/{_encode_id(policy_id)}": Response(200, submodel),
        f"/submodels/{_encode_id(f'urn:decentralabs:lab:{lab_id}:sm:simulationModels')}": Response(404, {}),
    })

    result = await resolver.resolve({"labId": lab_id, "accessKey": "motor.fmu"}, metadata)

    assert result["policySource"] == "aas-generated"
    assert result["variables"]["speed"]["read"] is True
    assert result["variables"]["command"]["writeAt"] == ["initialization", "runtime"]
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_path_like_fmu_access_key_falls_back_to_safe_lab_id_link(tmp_path, monkeypatch, metadata):
    lab_id = "local_demo_0123456789abcdef01234567"
    shell_id = _aas_id_for_lab(lab_id)
    policy_id = _submodel_id_for_access_control(lab_id)
    simulation_id = f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"
    shell = {
        "id": shell_id,
        "submodels": [
            {"keys": [{"type": "Submodel", "value": policy_id}]},
            {"keys": [{"type": "Submodel", "value": simulation_id}]},
        ],
    }
    policy_submodel = build_simulation_access_control_submodel(lab_id, metadata)

    import fmu_aas_generator
    monkeypatch.setattr(fmu_aas_generator, "BASYX_AAS_URL", "http://basyx-aas-server:8081")
    client = Client({
        f"/shells/{_encode_id(shell_id)}": Response(200, shell),
        f"/submodels/{_encode_id(policy_id)}": Response(200, policy_submodel),
    })

    def get_link_path(key):
        if "/" in key:
            raise ValueError("FMU path cannot be used directly as a link filename")
        return tmp_path / f"{key}.aas-link.json"

    (tmp_path / f"{lab_id}.aas-link.json").write_text(json.dumps({
        "aasId": shell_id,
        "labId": lab_id,
        "submodelIds": [policy_id, simulation_id],
        "accessControlSubmodelId": policy_id,
    }), encoding="utf-8")
    resolver = AasAccessPolicyResolver(
        get_basyx_url=lambda: fmu_aas_generator.BASYX_AAS_URL,
        get_request_headers=lambda: {},
        get_link_path=get_link_path,
        client_factory=lambda **_kwargs: client,
    )

    result = await resolver.resolve({
        "labId": lab_id,
        "accessKey": "local-demos/dc-motor/linux64/DC_motor.fmu",
    }, metadata)

    assert result["policySource"] == "aas-generated"
    assert result["variables"]["command"]["writeAt"] == ["initialization", "runtime"]


@pytest.mark.asyncio
async def test_generated_policy_can_reference_imported_simulation_models_submodel_id(tmp_path, monkeypatch, metadata):
    lab_id = "42"
    shell_id = "urn:external:aas:42"
    policy_id = _submodel_id_for_access_control(lab_id)
    simulation_id = "urn:provider:simulation-models:42"
    (tmp_path / "motor.fmu.aas-link.json").write_text(json.dumps({
        "aasId": shell_id,
        "labId": lab_id,
    }), encoding="utf-8")
    shell = {
        "id": shell_id,
        "submodels": [
            {"keys": [{"type": "Submodel", "value": policy_id}]},
            {"keys": [{"type": "Submodel", "value": simulation_id}]},
        ],
    }
    submodel = build_simulation_access_control_submodel(
        lab_id,
        metadata,
        simulation_model_submodel_id=simulation_id,
    )
    resolver, _ = make_resolver(tmp_path, monkeypatch, {
        f"/shells/{_encode_id(shell_id)}": Response(200, shell),
        f"/submodels/{_encode_id(policy_id)}": Response(200, submodel),
        f"/submodels/{_encode_id(simulation_id)}": Response(404, {}),
    })

    result = await resolver.resolve({"labId": lab_id, "accessKey": "motor.fmu"}, metadata)

    assert result["policySource"] == "aas-generated"
    assert result["variables"]["speed"]["read"] is True


@pytest.mark.asyncio
async def test_missing_aas_policy_uses_fmi_default(tmp_path, monkeypatch, metadata):
    import fmu_aas_generator

    monkeypatch.setattr(fmu_aas_generator, "BASYX_AAS_URL", "")
    resolver = AasAccessPolicyResolver(
        get_basyx_url=lambda: "",
        get_request_headers=lambda: {},
        get_link_path=lambda key: tmp_path / f"{key}.aas-link.json",
    )

    result = await resolver.resolve({"labId": "42", "accessKey": "motor.fmu"}, metadata)

    assert result["policySource"] == "fmi-default"
    assert result["variables"]["speed"]["read"] is True

    status = await resolver.inspect({"labId": "42", "accessKey": "motor.fmu"}, metadata)
    assert status == {
        "state": "fmi-default",
        "policySource": "fmi-default",
        "message": "No AAS access policy is linked; FMI-derived defaults are active.",
        "aasLinked": False,
        "regenerationAvailable": True,
        "readableVariableCount": 2,
        "writableVariableCount": 1,
    }


@pytest.mark.asyncio
async def test_linked_provider_policy_is_resolved_and_conditioned_on_verified_claims(tmp_path, monkeypatch, metadata):
    lab_id = "42"
    shell_id = "urn:external:aas:42"
    policy_id = _submodel_id_for_access_control(lab_id)
    simulation_model_id = f"urn:decentralabs:lab:{lab_id}:sm:simulationModels"
    (tmp_path / "motor.fmu.aas-link.json").write_text(json.dumps({
        "aasId": shell_id,
        "labId": lab_id,
        "accessControlSubmodelId": policy_id,
    }), encoding="utf-8")
    shell = {
        "id": shell_id,
        "submodels": [
            {"keys": [{"type": "Submodel", "value": policy_id}]},
            {"keys": [{"type": "Submodel", "value": simulation_model_id}]},
        ],
    }
    submodel = build_simulation_access_control_submodel(lab_id, metadata)
    rules_blob = next(item for item in submodel["submodelElements"] if item.get("modelType") == "Blob")
    rules = json.loads(base64.b64decode(rules_blob["value"]))
    rules["AllAccessPermissionRules"]["rules"][0]["FORMULA"] = {
        "$eq": [{"$attribute": {"CLAIM": "institution"}}, {"$strVal": "north-campus"}]
    }
    rules["AllAccessPermissionRules"]["rules"][0]["ACL"]["ATTRIBUTES"] = [{"CLAIM": "institution"}]
    rules_blob["value"] = base64.b64encode(json.dumps(rules).encode()).decode()
    resolver, _ = make_resolver(tmp_path, monkeypatch, {
        f"/shells/{_encode_id(shell_id)}": Response(200, shell),
        f"/submodels/{_encode_id(policy_id)}": Response(200, submodel),
    })

    result = await resolver.resolve(
        {"labId": lab_id, "accessKey": "motor.fmu", "institution": "north-campus"},
        metadata,
    )

    assert result["policySource"] == "aas-provider"
    assert result["variables"]["speed"]["read"] is True


@pytest.mark.asyncio
async def test_resolves_referenced_external_part4_blob_with_nonstandard_id_and_no_gateway_digest(
    tmp_path, monkeypatch, metadata,
):
    lab_id = "42"
    shell_id = "urn:external:aas:42"
    policy_id = "urn:external:submodel:access-policy"
    simulation_id = "urn:external:submodel:simulation-models"
    (tmp_path / "motor.fmu.aas-link.json").write_text(json.dumps({
        "aasId": shell_id,
        "labId": lab_id,
    }), encoding="utf-8")
    shell = {
        "id": shell_id,
        "submodels": [
            {"keys": [{"type": "Submodel", "value": policy_id}]},
            {"keys": [{"type": "Submodel", "value": simulation_id}]},
        ],
    }
    rules = build_part4_access_rules(metadata, simulation_id)
    submodel = {
        "id": policy_id,
        "idShort": "PartnerAccessRules",
        "semanticId": {"keys": [{"type": "GlobalReference", "value": "urn:partner:access-rules"}]},
        "modelType": "Submodel",
        "submodelElements": [{
            "idShort": "PartnerJsonRules",
            "modelType": "Blob",
            "contentType": "application/json",
            "value": base64.b64encode(json.dumps(rules).encode()).decode(),
        }],
    }
    resolver, client = make_resolver(tmp_path, monkeypatch, {
        f"/shells/{_encode_id(shell_id)}": Response(200, shell),
        f"/submodels/{_encode_id(simulation_id)}": Response(404, {}),
        f"/submodels/{_encode_id(policy_id)}": Response(200, submodel),
    })

    result = await resolver.resolve({"labId": lab_id, "accessKey": "motor.fmu"}, metadata)

    assert result["policySource"] == "aas-provider"
    assert result["variables"]["speed"]["read"] is True
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_linked_aas_unavailable_fails_closed(tmp_path, monkeypatch, metadata):
    import fmu_aas_generator

    monkeypatch.setattr(fmu_aas_generator, "BASYX_AAS_URL", "")
    (tmp_path / "motor.fmu.aas-link.json").write_text(
        json.dumps({"aasId": "urn:external:aas:42", "labId": "42"}),
        encoding="utf-8",
    )
    resolver = AasAccessPolicyResolver(
        get_basyx_url=lambda: "",
        get_request_headers=lambda: {},
        get_link_path=lambda key: tmp_path / f"{key}.aas-link.json",
    )

    with pytest.raises(RuntimeError, match="linked AAS access policy is unavailable"):
        await resolver.resolve({"labId": "42", "accessKey": "motor.fmu"}, metadata)

    status = await resolver.inspect({"labId": "42", "accessKey": "motor.fmu"}, metadata)
    assert status["state"] == "unavailable"
    assert status["aasLinked"] is True
    assert "AAS endpoint, credentials" in status["message"]
    assert status["regenerationAvailable"] is False


@pytest.mark.asyncio
async def test_inspect_reports_invalid_saved_aas_link_for_lab_manager(tmp_path, metadata):
    (tmp_path / "motor.fmu.aas-link.json").write_text("not json", encoding="utf-8")
    resolver = AasAccessPolicyResolver(
        get_basyx_url=lambda: "https://basyx.example",
        get_request_headers=lambda: {},
        get_link_path=lambda key: tmp_path / f"{key}.aas-link.json",
    )

    status = await resolver.inspect({"labId": "42", "accessKey": "motor.fmu"}, metadata)

    assert status == {
        "state": "invalid",
        "policySource": "unavailable",
        "message": "The saved AAS link is invalid. Review and save the link again before relying on its access rules.",
        "aasLinked": True,
        "regenerationAvailable": False,
        "readableVariableCount": 0,
        "writableVariableCount": 0,
    }
