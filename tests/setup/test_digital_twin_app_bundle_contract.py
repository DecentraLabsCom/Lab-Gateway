import json
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import sync_fmu_examples


def write_webapp(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return path


def test_webapp_bundle_validator_accepts_a_complete_local_asset_graph(tmp_path):
    archive = write_webapp(tmp_path / "complete.webapp.zip", {
        "index.html": '<link rel="stylesheet" href="./styles.css"><script type="module" src="./app.js"></script>',
        "app.js": "import { postToHost } from './digitalTwinAppProtocol.js'; import './scene.js';",
        "digitalTwinAppProtocol.js": "export function postToHost() {}",
        "scene.js": "export const scene = {};",
        "styles.css": ".scene { background-image: url('./texture.png'); }",
        "texture.png": "image-bytes",
    })

    files = sync_fmu_examples.validate_webapp_bundle(archive)

    assert "digitalTwinAppProtocol.js" in files


def test_webapp_bundle_validator_reports_a_missing_transitive_module(tmp_path):
    archive = write_webapp(tmp_path / "missing-module.webapp.zip", {
        "index.html": '<script type="module" src="./app.js"></script>',
        "app.js": "import './digitalTwinAppProtocol.js';",
    })

    with pytest.raises(ValueError, match=r"app\.js.*digitalTwinAppProtocol\.js"):
        sync_fmu_examples.validate_webapp_bundle(archive)


def test_webapp_bundle_validator_rejects_external_runtime_dependencies(tmp_path):
    archive = write_webapp(tmp_path / "external-module.webapp.zip", {
        "index.html": '<script type="module" src="./app.js"></script>',
        "app.js": "import { Scene } from 'three';",
    })

    with pytest.raises(ValueError, match="unbundled module import"):
        sync_fmu_examples.validate_webapp_bundle(archive)


def test_webapp_bundle_validator_accepts_the_canonical_sdk_copy(tmp_path, monkeypatch):
    sdk_directory = tmp_path / "digital-twin-app-protocol"
    sdk_directory.mkdir()
    sdk_source = "export function postToHost() {}"
    (sdk_directory / "package.json").write_text(json.dumps({"browserBundleFile": "digitalTwinAppProtocol.js"}), encoding="utf-8")
    (sdk_directory / "index.js").write_text(sdk_source, encoding="utf-8")
    monkeypatch.setattr(sync_fmu_examples, "MARKETPLACE_PROTOCOL_PACKAGE", sdk_directory)
    archive = write_webapp(tmp_path / "canonical-sdk.webapp.zip", {
        "index.html": '<script type="module" src="./app.js"></script>',
        "app.js": "import { postToHost } from './digitalTwinAppProtocol.js';",
        "digitalTwinAppProtocol.js": sdk_source,
    })

    files = sync_fmu_examples.validate_webapp_bundle(archive, verify_protocol_sdk=True)

    assert "digitalTwinAppProtocol.js" in files


def test_webapp_bundle_validator_rejects_a_stale_sdk_copy(tmp_path, monkeypatch):
    sdk_directory = tmp_path / "digital-twin-app-protocol"
    sdk_directory.mkdir()
    (sdk_directory / "package.json").write_text(json.dumps({"browserBundleFile": "digitalTwinAppProtocol.js"}), encoding="utf-8")
    (sdk_directory / "index.js").write_text("export const protocolVersion = 1", encoding="utf-8")
    monkeypatch.setattr(sync_fmu_examples, "MARKETPLACE_PROTOCOL_PACKAGE", sdk_directory)
    archive = write_webapp(tmp_path / "stale-sdk.webapp.zip", {
        "index.html": '<script type="module" src="./app.js"></script>',
        "app.js": "import { protocolVersion } from './digitalTwinAppProtocol.js';",
        "digitalTwinAppProtocol.js": "export const protocolVersion = 0",
    })

    with pytest.raises(ValueError, match="stale Marketplace SDK module"):
        sync_fmu_examples.validate_webapp_bundle(archive, verify_protocol_sdk=True)
