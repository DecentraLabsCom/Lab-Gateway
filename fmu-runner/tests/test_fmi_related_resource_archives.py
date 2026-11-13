"""Bounded, local-only REF companions and STRUCT maps from untrusted FMUs."""

from copy import deepcopy
import warnings
import xml.etree.ElementTree as ET
import zipfile

import pytest

import fmi_ls_ref as ref
import fmi_ls_struct as struct


def _fmu(tmp_path, entries):
    path = tmp_path / "source.fmu"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in entries:
                archive.writestr(name, value)
    return path


def _references(*sources):
    root = ET.Element("fmiReferences", {"{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-name": "org.fmi-standard.fmi-ls-ref",
                                          "{http://fmi-standard.org/fmi-ls-manifest}fmi-ls-version": "1.0.0"})
    ET.SubElement(root, "Ignored")
    for source, media in sources:
        related = ET.SubElement(root, "Related", {"source": source, "type": media, "role": "visualization", "description": "Scene"})
        ET.SubElement(related, "Label", {"name": " Preview ", "description": " Rendered model "})
        ET.SubElement(related, "Label")
    return ET.tostring(root)


def test_ref_prefers_webapp_and_keeps_stable_resource_identity(tmp_path):
    manifest = _references(("../../resources/model.glb", "MODEL/GLTF-BINARY; version=2"),
                           ("../../resources/model.webapp.zip", "application/zip"),
                           ("../../resources/model.glb", "MODEL/GLTF-BINARY; version=2"))
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, manifest), ("resources/model.glb", b"scene"), ("resources/model.webapp.zip", b"webapp")])
    discovery = ref.read_related_resources(path)
    assert discovery["manifestName"] == "org.fmi-standard.fmi-ls-ref"
    assert discovery["manifestVersion"] == "1.0.0"
    assert all(item["availableInFmu"] for item in discovery["resources"])
    assert discovery["resources"][0]["labels"] == [{"name": "Preview", "description": "Rendered model"}]
    assert discovery["resources"][2]["id"] == discovery["resources"][0]["id"] + "_2"
    assert ref.read_visual_asset(path) == (b"webapp", "threejs-app", "fmi-ls-ref")


@pytest.mark.parametrize("source", [
    "https://example.org/model.glb", "//example.org/model.glb", "/model.glb", "../../../../escape.glb",
    "../../resources/model.glb?token=secret", "../../resources/model.glb#fragment",
    "..\\model.glb", "../../resources/%5cmodel.glb", "../../resources/%00model.glb", "",
])
def test_ref_never_exposes_external_traversing_or_ambiguous_resource_paths(tmp_path, source):
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, _references((source, "model/gltf-binary")))])
    assert ref.read_related_resources(path)["resources"] == []
    assert ref.read_visual_asset(path) is None


def test_ref_rejects_duplicate_missing_and_oversized_companions(tmp_path, monkeypatch):
    manifest = _references(("../../resources/app.webapp.zip", "application/zip"), ("../../resources/model.glb", "model/gltf-binary"))
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, manifest), ("resources/app.webapp.zip", b"too large"), ("resources/model.glb", b"glb")])
    monkeypatch.setattr(ref, "MAX_ASSET_BYTES", 3)
    assert ref.read_visual_asset(path) == (b"glb", "glb", "fmi-ls-ref")
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, manifest), ("resources/model.glb", b"one"), ("resources/model.glb", b"two")])
    assert ref.read_visual_asset(path) is None
    assert not any(item["availableInFmu"] for item in ref.read_related_resources(path)["resources"])


@pytest.mark.parametrize("manifest", [b"<invalid>", b"<wrong/>", b'<!DOCTYPE fmiReferences><fmiReferences/>',
                                     b'<fmiReferences xmlns:ls="http://fmi-standard.org/fmi-ls-manifest" ls:fmi-ls-name="other"/>'])
def test_ref_invalid_or_entity_bearing_manifests_are_ignored(tmp_path, manifest):
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, manifest)])
    assert ref.read_related_resources(path)["resources"] == []
    assert ref.read_visual_asset(path) is None


def test_ref_manifest_and_discovery_limits_apply_before_asset_reads(tmp_path, monkeypatch):
    path = _fmu(tmp_path, [(ref.MANIFEST_PATH, _references(*[(f"../../resources/{i}.glb", "model/gltf-binary") for i in range(3)]))])
    monkeypatch.setattr(ref, "MAX_RELATED_RESOURCES", 2)
    assert len(ref.read_related_resources(path)["resources"]) == 2
    monkeypatch.setattr(ref, "MAX_MANIFEST_BYTES", 10)
    assert ref.read_related_resources(path)["manifestName"] is None
    assert ref.read_visual_asset(path) is None
    assert ref.read_visual_asset(tmp_path / "missing.fmu") is None


STRUCT = "org.fmi-standard.fmi-ls-struct"


def _map():
    return {"manifestName": STRUCT, "manifestVersion": "1.0", "maps": [{
        "name": "Lookup", "terminalKind": STRUCT + ".map.rectilinearGrid", "matchingRule": STRUCT + ".map",
        "members": [{"variableName": "x", "memberName": "axis", "variableKind": STRUCT + ".map.domain", "orderingConstraint": "strictlyIncreasing"},
                    {"variableName": "u", "memberName": "argument", "variableKind": STRUCT + ".map.domainInput"},
                    {"variableName": "y", "memberName": "values", "variableKind": STRUCT + ".map.codomain"},
                    {"variableName": "v", "memberName": "result", "variableKind": STRUCT + ".map.codomainOutput"}],
    }]}


def _struct_entries(terminals):
    manifest = f'<fmiLayeredStandardManifest xmlns:ls="http://fmi-standard.org/fmi-ls-manifest" ls:fmi-ls-name="{STRUCT}" ls:fmi-ls-version="1.0"/>'
    return [(struct.MANIFEST_PATH, manifest), (struct.TERMINALS_PATH, terminals)]


def test_struct_reader_retains_valid_axes_pairing_and_ordering_annotations(tmp_path):
    terminals = f'''<fmiTerminalsAndIcons fmiVersion="3.0"><Terminals><Ignored/>
      <Terminal name="Lookup" terminalKind="{STRUCT}.map.rectilinearGrid" matchingRule="{STRUCT}.map">
        <Ignored/><TerminalMemberVariable variableName="x" memberName="axis" variableKind="{STRUCT}.map.domain">
          <Annotations><Annotation type="{STRUCT}.orderingConstraint">strictlyIncreasing</Annotation></Annotations>
        </TerminalMemberVariable>
        <TerminalMemberVariable variableName="u" memberName="argument" variableKind="{STRUCT}.map.domainInput"/>
        <TerminalMemberVariable variableName="y" memberName="values" variableKind="{STRUCT}.map.codomain"/>
        <TerminalMemberVariable variableName="v" memberName="result" variableKind="{STRUCT}.map.codomainOutput"/>
      </Terminal></Terminals></fmiTerminalsAndIcons>'''
    path = _fmu(tmp_path, _struct_entries(terminals))
    assert struct.read_fmi_ls_struct(path, fmi_version="3.0", variable_names=["x", "u", "y", "v"]) == _map()
    assert struct.read_fmi_ls_struct(path, fmi_version="2.0") is None
    assert struct.read_fmi_ls_struct(path, fmi_version="3.0", variable_names=["x"])["maps"] == []


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(matchingRule="unknown"), lambda m: m.update(terminalKind="unknown"),
    lambda m: m.update(members=[]), lambda m: m["members"][0].update(variableName="unknown"),
    lambda m: m["members"][1].update(memberName="axis"),
    lambda m: m["members"][1].update(variableName="x"),
    lambda m: m["members"][0].update(orderingConstraint="unknown"),
    lambda m: m["members"][2].update(orderingConstraint="increasing"),
    lambda m: m["members"].reverse(), lambda m: m["members"].pop(2),
    lambda m: m["members"][1].update(variableKind=STRUCT + ".map.unsupported"),
])
def test_struct_rejects_unknown_variables_duplicate_members_and_invalid_map_topologies(mutate):
    value = deepcopy(_map())
    mutate(value["maps"][0])
    assert struct.normalize_fmi_ls_struct(value, variable_names=["x", "u", "y", "v"])["maps"] == []


@pytest.mark.parametrize("terminals", [b"invalid", b'<!DOCTYPE x><fmiTerminalsAndIcons/>',
                                     b'<fmiTerminalsAndIcons fmiVersion="2.0"/>', b"<wrong/>"])
def test_struct_invalid_xml_and_wrong_fmi_versions_do_not_create_maps(tmp_path, terminals):
    assert struct.read_fmi_ls_struct(_fmu(tmp_path, _struct_entries(terminals)), fmi_version="3.0") is None


def test_struct_rejects_duplicate_members_in_archive_and_honors_size_limits(tmp_path, monkeypatch):
    entries = _struct_entries('<fmiTerminalsAndIcons fmiVersion="3.0"/>')
    path = _fmu(tmp_path, entries + entries[:1])
    assert struct.read_fmi_ls_struct(path, fmi_version="3.0") is None
    path = _fmu(tmp_path, entries)
    monkeypatch.setattr(struct, "MAX_XML_BYTES", 10)
    assert struct.read_fmi_ls_struct(path, fmi_version="3.0") is None
    assert struct.read_fmi_ls_struct(tmp_path / "missing.fmu", fmi_version="3.0") is None
