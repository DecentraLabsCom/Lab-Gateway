"""Local demo provisioning keeps visual companions inside the selected FMU root."""

import hashlib
import json
import struct
import zipfile

import pytest

from digital_twin_assets_router import _node_morph_target_count, store_local_preview_assets


KEY = "model.fmu"
LAB = "local_demo_" + hashlib.sha256(KEY.encode()).hexdigest()[:24]


def _glb():
    content = json.dumps({"asset": {"version": "2.0"}}).encode()
    content += b" " * (-len(content) % 4)
    return struct.pack("<4sII", b"glTF", 2, 20 + len(content)) + struct.pack("<II", len(content), 0x4E4F534A) + content


def test_local_preview_stores_both_companion_modes_under_its_synthetic_lab_id(tmp_path):
    data = tmp_path / "fmus"
    data.mkdir()
    fmu = data / KEY
    with zipfile.ZipFile(fmu, "w") as archive:
        archive.writestr("modelDescription.xml", '<fmiModelDescription fmiVersion="3.0"/>')
    scene = _glb()
    fmu.with_suffix(".glb").write_bytes(scene)
    with zipfile.ZipFile(fmu.with_suffix(".webapp.zip"), "w") as archive:
        archive.writestr("index.html", '<!doctype html><html><script type="module" src="./app.js"></script></html>')
        archive.writestr("app.js", "window.ready = true;")
    root = tmp_path / "assets"
    result = store_local_preview_assets(root=root, lab_id=LAB, access_key=KEY,
        fmu_data_root=data, resolve_local_fmu_path=lambda key: data / key)
    assert [item["renderer"] for item in result] == ["threejs-app", "glb"]
    assert result[0]["path"].startswith("/digital-twin-apps/" + LAB + "/")
    assert result[1]["path"].startswith("/digital-twin-scenes/" + LAB + "/")
    stored_scenes = list(root.rglob("*.glb"))
    assert len(stored_scenes) == 1
    assert stored_scenes[0].read_bytes() == scene
    assert any(p.read_bytes() == b"window.ready = true;" for p in root.rglob("app.js"))
    assert store_local_preview_assets(root=root, lab_id=LAB, access_key=KEY,
        fmu_data_root=data, resolve_local_fmu_path=None) == []


@pytest.mark.parametrize("lab", ["42", "local_demo_invalid", "local_demo_" + "b" * 24])
def test_public_or_mismatched_lab_ids_cannot_be_used_for_local_preview_storage(tmp_path, lab):
    with pytest.raises(ValueError, match="laboratory ID"):
        store_local_preview_assets(root=tmp_path / "assets", lab_id=lab, access_key=KEY,
            fmu_data_root=tmp_path, resolve_local_fmu_path=lambda _: tmp_path / KEY)


def test_missing_fmus_and_companions_are_optional_but_an_outside_resolver_is_rejected(tmp_path):
    data = tmp_path / "fmus"
    data.mkdir()
    root = tmp_path / "assets"
    assert store_local_preview_assets(root=root, lab_id=LAB, access_key=KEY,
        fmu_data_root=data, resolve_local_fmu_path=lambda _: data / KEY) == []
    (data / KEY).write_bytes(b"no-companions")
    assert store_local_preview_assets(root=root, lab_id=LAB, access_key=KEY,
        fmu_data_root=data, resolve_local_fmu_path=lambda _: data / KEY) == []
    outside = tmp_path / KEY
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="companion asset path"):
        store_local_preview_assets(root=root, lab_id=LAB, access_key=KEY,
            fmu_data_root=data, resolve_local_fmu_path=lambda _: outside)
    assert not root.exists()


def test_morph_bindings_use_one_consistent_arity_for_mesh_primitives_and_node_weights():
    mesh = {"primitives": [{"targets": [{}, {}]}, {"targets": [{}, {}]}], "weights": [0.0, 0.0]}
    assert _node_morph_target_count({"meshes": [mesh]}, {"mesh": 0, "weights": [0.0, 0.0]}) == 2
    assert _node_morph_target_count({"meshes": [mesh]}, {"mesh": 0, "weights": [0.0]}) is None
    mesh["weights"] = [0.0]
    assert _node_morph_target_count({"meshes": [mesh]}, {"mesh": 0}) is None


@pytest.mark.parametrize("document,node", [
    ({}, {"mesh": 0}), ({"meshes": []}, {"mesh": 0}),
    ({"meshes": [{}]}, {"mesh": True}), ({"meshes": [{}]}, {"mesh": -1}),
    ({"meshes": [None]}, {"mesh": 0}), ({"meshes": [{}]}, {"mesh": 0}),
    ({"meshes": [{"primitives": []}]}, {"mesh": 0}),
    ({"meshes": [{"primitives": [None]}]}, {"mesh": 0}),
    ({"meshes": [{"primitives": [{"targets": "bad"}]}]}, {"mesh": 0}),
    ({"meshes": [{"primitives": [{"targets": []}]}]}, {"mesh": 0}),
    ({"meshes": [{"primitives": [{"targets": [{}]}, {"targets": [{}, {}]}]}]}, {"mesh": 0}),
])
def test_invalid_or_inconsistent_morph_topologies_do_not_advertise_a_binding_arity(document, node):
    assert _node_morph_target_count(document, node) is None
