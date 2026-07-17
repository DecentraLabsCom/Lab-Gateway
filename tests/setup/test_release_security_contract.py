"""Regression checks for the release/security controls tracked in H-05."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_rebuilds_and_verifies_promoted_native_runtimes():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "cmake --build /workspace/build-ci" in release
    assert "cmp --silent" in release
    assert "Promoted win64 runtime differs" in release


def test_release_emits_sbom_and_provenance_attestation():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "anchore/sbom-action" in release
    assert "actions/attest-build-provenance" in release
    assert "sbom.cdx.json" in release
    assert "sbom.cdx.json.sha256" in release


def test_security_workflow_covers_actions_python_cpp_and_pip_audit():
    security = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    assert "actions,java,javascript,python,cpp" in security
    assert "pip-audit -r fmu-runner/requirements.txt" in security
    assert "pip-audit -r ops-worker/requirements.txt" in security
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0" in security
    assert "github/codeql-action/init@eec0bff2f6c15bf3f1e8a0152f94d17664a06a06" in security
    assert "cmake --build fmu-proxy-runtime-src/build-codeql" in security


def test_all_workflow_actions_are_pinned_to_commits():
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "uses:" in line:
                ref = line.split("@", 1)[1].split()[0]
                assert not ref.startswith("v"), f"Unpinned action in {workflow}: {line}"


def test_remote_guacamole_war_is_checksum_verified_and_images_are_versioned():
    dockerfile = (ROOT / "guacamole" / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "GUACAMOLE_WAR_SHA256" in dockerfile
    assert "sha256sum -c -" in dockerfile
    assert "guacamole/guacd:1.6.0" in compose
    assert "certbot/certbot:v2.11.0" in compose
    assert "mongo:7.0.14" in compose
