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
    # The embedded blockchain-services submodule is intentionally excluded by
    # the CodeQL config; this workflow covers the Gateway's supported sources.
    assert "actions,javascript,python,cpp" in security
    assert "pip-audit -r fmu-runner/requirements.txt" in security
    assert "pip-audit -r ops-worker/requirements.txt" in security
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in security
    assert "github/codeql-action/init@cdf488f595d80d6e07e03d4674febd5ab45fa938" in security
    assert "cmake --build fmu-proxy-runtime-src/build-codeql" in security


def test_native_ci_jobs_use_the_preinstalled_runner_toolchain():
    security = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    gateway_tests = (ROOT / ".github" / "workflows" / "gateway-tests.yml").read_text(encoding="utf-8")

    codeql_job = security.split("\n  python-audit:", 1)[0]
    native_tests_job = gateway_tests.split("\n  native-runtime-unit-tests:", 1)[1].split(
        "\n  ops-worker-tests:", 1
    )[0]

    for workflow, job in (("security", codeql_job), ("gateway-tests", native_tests_job)):
        assert "runs-on: ubuntu-24.04" in job, f"{workflow} must pin the native runner image"
        assert "sudo apt-get" not in job, f"{workflow} must not depend on APT availability"
        assert "Verify native runtime toolchain" in job


def test_ops_worker_summary_requires_a_completed_checkout():
    workflow = (ROOT / ".github" / "workflows" / "gateway-tests.yml").read_text(encoding="utf-8")
    guard = "if: always() && hashFiles('.github/scripts/test_summary.py') != ''"

    assert workflow.count(guard) == 2


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
