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



def test_webapp_bundle_validator_accepts_direct_messages_without_an_sdk(tmp_path):
    archive = write_webapp(tmp_path / "messages-only.webapp.zip", {
        "index.html": '<script type="module" src="./viewer.js"></script>',
        "viewer.js": "window.parent.postMessage({type: 'decentralabs:digital-twin-ready', version: 1}, '*');",
    })

    assert sync_fmu_examples.validate_webapp_bundle(archive) == {"index.html", "viewer.js"}


def test_webapp_bundle_validator_accepts_a_separately_bundled_client(tmp_path):
    archive = write_webapp(tmp_path / "optional-client.webapp.zip", {
        "index.html": '<script type="module" src="./viewer.js"></script>',
        "viewer.js": "import { connect } from './custom/client.js'; connect();",
        "custom/client.js": "export function connect() {}",
    })

    assert "custom/client.js" in sync_fmu_examples.validate_webapp_bundle(archive)
