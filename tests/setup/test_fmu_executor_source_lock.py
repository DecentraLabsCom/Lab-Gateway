import json
import re
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_LOCK = GATEWAY_ROOT / "fmu-executor" / "SOURCE.lock.json"


def test_executor_image_defaults_match_the_canonical_release_lock():
    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    image = lock["containerImage"]
    reference = image["reference"]

    assert lock["schemaVersion"] == 1
    assert lock["repository"] == "DecentraLabsCom/FMU-Executor"
    assert lock["runtimeDownloads"] is False
    assert image["repository"] == "ghcr.io/decentralabscom/fmu-executor"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"])
    assert reference == f"{image['repository']}:{lock['version']}@{image['digest']}"

    compose = (GATEWAY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"image: ${{FMU_EXECUTOR_IMAGE:-{reference}}}" in compose

    env_example = (GATEWAY_ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"FMU_EXECUTOR_IMAGE={reference}" in env_example

    setup_shell = (GATEWAY_ROOT / "setup.sh").read_text(encoding="utf-8")
    assert f'fmu_executor_image="{reference}"' in setup_shell

    setup_batch = (GATEWAY_ROOT / "setup.bat").read_text(encoding="utf-8")
    assert f'set "fmu_executor_image={reference}"' in setup_batch

    default_docs = (
        GATEWAY_ROOT / "fmu-runner" / "README.md",
        GATEWAY_ROOT / "docs" / "install" / "install-manual-compose.md",
        GATEWAY_ROOT / "docs" / "install" / "instalar-compose-manual.md",
        GATEWAY_ROOT / "docs" / "reference" / "configuration.md",
    )
    for path in default_docs:
        assert "fmu-executor/SOURCE.lock.json" in path.read_text(encoding="utf-8"), path
