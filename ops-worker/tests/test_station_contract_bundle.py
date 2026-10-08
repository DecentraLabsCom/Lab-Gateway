import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_station_contract_bundle.py"
SPEC = importlib.util.spec_from_file_location("station_contract_bundle", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _bundle(tmp_path):
    station = tmp_path / "station"
    source = tmp_path / "gateway"
    relative_source = "contracts/station/dispatcher/v2/request.schema.json"
    relative_target = "gateway-contracts/dispatcher/v2/request.schema.json"
    content = b'{"schemaVersion":2}\n'
    source_file = source / relative_source
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(content)
    target_file = station / "contracts" / "station" / relative_target
    target_file.parent.mkdir(parents=True)
    target_file.write_bytes(content)

    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Contract test"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "contract-test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(source), "add", relative_source], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    lock = station / "contracts" / "station" / "schema-bundle.lock.json"
    lock.write_text(json.dumps({
        "schemaVersion": 1,
        "repository": "DecentraLabsCom/Lab-Gateway",
        "commit": commit,
        "files": [{
            "source": relative_source,
            "target": relative_target,
            "sha256": hashlib.sha256(content).hexdigest(),
        }],
    }), encoding="utf-8")
    return station, source, lock, target_file


def test_contract_bundle_passes_offline_and_against_the_pinned_gateway_commit(tmp_path):
    station, source, lock, _ = _bundle(tmp_path)

    MODULE.verify_bundle(station, lock)
    MODULE.verify_bundle(station, lock, source)


def test_contract_bundle_rejects_modified_or_unlisted_local_files(tmp_path):
    station, _, lock, target = _bundle(tmp_path)
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        MODULE.verify_bundle(station, lock)

    target.write_bytes(b'{"schemaVersion":2}\n')
    extra = target.parent / "unreviewed.schema.json"
    extra.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="file set differs"):
        MODULE.verify_bundle(station, lock)


def test_contract_bundle_rejects_a_gateway_checkout_at_the_wrong_revision(tmp_path):
    station, source, lock, _ = _bundle(tmp_path)
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["commit"] = "0" * 40
    lock.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="revision does not match"):
        MODULE.verify_bundle(station, lock, source)

    MODULE.verify_bundle(station, lock)
