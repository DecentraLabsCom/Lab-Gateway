from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FMU_INTEGRATION_COMPOSE = REPO_ROOT / "tests" / "integration" / "docker-compose.fmu-integration.yml"


def test_fmu_integration_compose_enables_the_fmu_runner_gateway_route():
    compose = FMU_INTEGRATION_COMPOSE.read_text(encoding="utf-8")

    assert "FMU_RUNNER_ENABLED: \"true\"" in compose
