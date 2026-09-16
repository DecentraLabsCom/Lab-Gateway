from pathlib import Path


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _local_runner_block() -> str:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    return compose.split("  fmu-runner-local:\n", 1)[1].split(
        "\n  # BaSyx AAS Server", 1
    )[0]


def test_local_fmu_runner_has_bundled_aas_configuration():
    block = _local_runner_block()

    assert (
        "- BASYX_AAS_URL=${BASYX_AAS_URL:-http://basyx-aas-server:8081}"
        in block
    )
    assert "      fmu_aas:\n" in block


def test_local_fmu_runner_keeps_control_plane_and_station_isolation():
    block = _local_runner_block()

    assert "      - fmu_control\n" not in block
    assert "      - fmu_station" not in block
