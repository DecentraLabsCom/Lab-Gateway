"""AAS projections expose usable resource descriptors, never hidden map data."""

from copy import deepcopy
import json

import pytest

from aas_model_builders import build_fmi_ls_related_resources_submodel, build_fmi_ls_struct_submodel


def _values(elements):
    return {element["idShort"]: element["value"] for element in elements}


def test_related_resources_keep_availability_labels_and_collision_free_identifiers():
    resource = {"source": "resources/scene.glb", "role": "visualization", "type": "model/gltf-binary",
                "description": "Scene", "availableInFmu": True,
                "labels": [None, {}, {"name": " Preview ", "description": " Model view "}]}
    result = build_fmi_ls_related_resources_submodel("42", {"manifestName": "org.fmi-standard.fmi-ls-ref",
        "manifestVersion": "1.0", "resources": [None, resource, deepcopy(resource)]})
    properties = _values(result["submodelElements"])
    assert properties["ManifestName"] == "org.fmi-standard.fmi-ls-ref"
    assert properties["ManifestVersion"] == "1.0"
    resources = properties["Resources"]
    assert len(resources) == 2
    assert resources[1]["idShort"] == resources[0]["idShort"] + "_2"
    fields = _values(resources[0]["value"])
    assert fields["Source"] == "resources/scene.glb"
    assert fields["AvailableInFmu"] == "true"
    assert _values(fields["Labels"][0]["value"]) == {"Name": "Preview", "Description": "Model view"}
    assert result["modelType"] == "Submodel"


@pytest.mark.parametrize("source", ["", "/etc/passwd", "https://outside.example/a", "//outside.example/a",
                                    "a?secret=1", "a#fragment", "a\\b", "a\0b", "a" * 2049])
def test_related_resource_index_drops_unusable_or_external_locations(source):
    result = build_fmi_ls_related_resources_submodel("42", {"manifestName": "org.fmi-standard.fmi-ls-ref",
        "resources": [{"source": source}]})
    assert _values(result["submodelElements"])["Resources"] == []


@pytest.mark.parametrize("payload", [None, [], {}, {"manifestName": "other"}])
def test_unrecognized_ref_manifests_do_not_create_an_aas_submodel(payload):
    assert build_fmi_ls_related_resources_submodel("42", payload) is None


def _struct():
    prefix = "org.fmi-standard.fmi-ls-struct"
    return {"manifestName": prefix, "manifestVersion": "1.0", "maps": [{
        "name": "Lookup", "terminalKind": prefix + ".map.rectilinearGrid", "matchingRule": prefix + ".map",
        "data": "private-map-values",
        "members": [{"variableName": "x", "memberName": "axis", "variableKind": prefix + ".map.domain", "orderingConstraint": "increasing", "values": [123456789]},
                    {"variableName": "y", "memberName": "values", "variableKind": prefix + ".map.codomain"}],
    }]}


def test_struct_projection_respects_read_permissions_and_does_not_copy_data_values():
    assert build_fmi_ls_struct_submodel("42", _struct(), readable_variable_names={"x"}) is None
    result = build_fmi_ls_struct_submodel("42", _struct(), readable_variable_names={"x", "y"})
    properties = _values(result["submodelElements"])
    maps = properties["Maps"]
    fields = _values(maps[0]["value"])
    assert fields["Name"] == "Lookup"
    members = fields["Members"]
    assert _values(members[0]["value"])["OrderingConstraint"] == "increasing"
    assert _values(members[1]["value"])["VariableName"] == "y"
    serialized = json.dumps(result)
    assert "private-map-values" not in serialized
    assert "123456789" not in serialized


@pytest.mark.parametrize("value", [None, {}, {"manifestName": "org.fmi-standard.fmi-ls-struct", "manifestVersion": "1.0", "maps": []}])
def test_empty_or_invalid_struct_manifest_is_not_advertised(value):
    assert build_fmi_ls_struct_submodel("42", value) is None
