from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"


def _service_block(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        text,
    )
    assert match, f"Missing Compose service {name}"
    return match.group("body")


def test_lite_does_not_depend_on_the_embedded_backend_for_local_ops_schema():
    compose = COMPOSE.read_text(encoding="utf-8")
    migrator = _service_block(compose, "ops-schema-migrator")
    backend = _service_block(compose, "blockchain-services")
    ops_worker = _service_block(compose, "ops-worker")

    assert "BLOCKCHAIN_MYSQL_DATABASE" in migrator
    assert "BLOCKCHAIN_MYSQL_USER" in migrator
    assert "blockchain_mysql_password" in migrator
    assert "condition: service_healthy" in migrator
    assert "mysql:" in migrator

    assert "ops-schema-migrator:" in backend
    assert "condition: service_completed_successfully" in backend
    assert "ops-schema-migrator:" in ops_worker
    assert "condition: service_completed_successfully" in ops_worker

    # Lite intentionally leaves the embedded Java process dormant, so the
    # schema migrator must be its independent prerequisite.
    assert "Embedded blockchain-services disabled (Lite mode); container is dormant." in compose
