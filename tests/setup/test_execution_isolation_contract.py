import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
ROOT_ENV = (ROOT / ".env.example").read_text(encoding="utf-8")


def _service_block(service_name: str) -> str:
    marker_match = re.search(rf"^  {re.escape(service_name)}:\s*$", COMPOSE, re.MULTILINE)
    assert marker_match is not None
    start = marker_match.end()
    next_service_match = re.search(r"^  [A-Za-z0-9_-]+:\s*$", COMPOSE[start:], re.MULTILINE)
    next_service = start + next_service_match.start() if next_service_match else -1
    return COMPOSE[start:] if next_service == -1 else COMPOSE[start:next_service]


def test_production_fmu_runner_is_station_only_and_keeps_control_networks_out_of_local_profile():
    production = _service_block("fmu-runner")
    local = _service_block("fmu-runner-local")

    assert 'profiles: ["fmu-runner"]' in production
    assert "FMU_BACKEND_MODE=station" in production
    assert "FMU_LOCAL_DEV_MODE" not in production
    assert "FMU_LOCAL_REALTIME_ENABLED" not in production

    assert 'profiles: ["fmu-local-dev"]' in local
    assert "FMU_BACKEND_MODE=local" in local
    assert "FMU_LOCAL_DEV_MODE=true" in local
    assert "fmu_control" not in local
    assert "fmu_aas" not in local
    assert "AUTH_SESSION_TICKET_INTERNAL_TOKEN" not in local
    assert "SESSION_OBSERVER_SIGNING_SECRET" not in local
    assert "FMU_STATION_INTERNAL_TOKEN" not in local
    assert "FMU_PROXY_SIGNING_KEY" not in local


def test_local_fmu_network_is_internal_and_openresty_is_the_only_shared_edge():
    openresty = _service_block("openresty")
    local = _service_block("fmu-runner-local")

    assert "fmu_local_edge" in openresty
    assert "fmu_local_edge" in local
    assert "fmu-runner" in local
    assert "fmu_local_edge:\n    driver: bridge\n    internal: true" in COMPOSE


def test_application_database_credentials_use_only_dedicated_secret_files():
    assert "GUACAMOLE_MYSQL_PASSWORD:-${MYSQL_PASSWORD}" not in COMPOSE
    assert "BLOCKCHAIN_MYSQL_PASSWORD:-${MYSQL_PASSWORD}" not in COMPOSE
    assert "OPS_BACKEND_MYSQL_PASSWORD:-${MYSQL_PASSWORD}" not in COMPOSE
    assert "OPS_GUACAMOLE_MYSQL_PASSWORD:-${MYSQL_PASSWORD}" not in COMPOSE
    assert "GUACAMOLE_MYSQL_PASSWORD_FILE: /run/secrets/guacamole_mysql_password" in COMPOSE
    assert "BLOCKCHAIN_MYSQL_PASSWORD_FILE: /run/secrets/blockchain_mysql_password" in COMPOSE
    assert "OPS_BACKEND_MYSQL_PASSWORD_FILE=/run/secrets/ops_backend_mysql_password" in COMPOSE
    assert "OPS_GUACAMOLE_MYSQL_PASSWORD_FILE=/run/secrets/ops_guacamole_mysql_password" in COMPOSE
    assert not re.search(r"^MYSQL_PASSWORD=", ROOT_ENV, re.MULTILINE)


def test_mysql_healthcheck_reads_passwords_from_mounted_secrets():
    mysql = _service_block("mysql")
    healthcheck = (ROOT / "mysql" / "healthcheck.sh").read_text(encoding="utf-8")

    assert "./mysql/healthcheck.sh:/usr/local/bin/mysql-healthcheck.sh:ro" in mysql
    assert 'test: ["CMD", "bash", "/usr/local/bin/mysql-healthcheck.sh"]' in mysql
    assert 'root_password="$(read_secret /run/secrets/mysql_root_password)"' in healthcheck
    assert 'blockchain_password="$(read_secret /run/secrets/blockchain_mysql_password)"' in healthcheck
    assert 'value="$(cat "$path")"' in healthcheck
    assert "mysqladmin ping" in healthcheck
    assert '-p"$root_password"' in healthcheck
    assert "mysql \\\n  -h localhost" in healthcheck
    assert '-u"$BLOCKCHAIN_MYSQL_USER"' in healthcheck
    assert '-p"$blockchain_password"' in healthcheck
    assert '-p"$${MYSQL_ROOT_PASSWORD}"' not in mysql
    assert '-p"$${BLOCKCHAIN_MYSQL_PASSWORD}"' not in mysql


def test_control_and_data_services_use_separate_internal_networks():
    openresty = _service_block("openresty")
    blockchain = _service_block("blockchain-services")
    mysql = _service_block("mysql")
    guacamole = _service_block("guacamole")
    guacd = _service_block("guacd")
    ops = _service_block("ops-worker")

    assert "gateway_public" in openresty
    assert "gateway_backend" in openresty
    assert "gateway_guacamole" in openresty
    assert "ops_control" in openresty

    assert "gateway_backend" in blockchain
    assert "database_backend" in blockchain
    assert "fmu_control" in blockchain
    assert "guacnet" not in blockchain

    assert "database_backend" in mysql
    assert "database_guacamole" in mysql
    assert "database_ops" in mysql
    assert "guacnet" not in mysql

    assert "gateway_guacamole" in guacamole
    assert "database_guacamole" in guacamole
    assert "guacd_net" in guacamole
    assert "guacnet" not in guacamole
    assert "guacd_net" in guacd

    assert "ops_control" in ops
    assert "ops_backend" in ops
    assert "database_ops" in ops
    assert "ops_guacamole" in ops
    assert "guacnet" not in ops


def test_fmu_and_ops_use_distinct_aas_edges():
    blockchain = _service_block("blockchain-services")
    ops = _service_block("ops-worker")
    production = _service_block("fmu-runner")
    basyx = _service_block("basyx-aas-server")

    assert "- fmu_aas\n" not in blockchain
    assert "- fmu_aas\n" in production
    assert "- fmu_aas\n" not in ops
    assert "fmu_aas_ops" in ops
    assert "fmu_aas" in basyx
    assert "fmu_aas_ops" in basyx
    assert "fmu_aas_ops:\n    driver: bridge\n    internal: true" in COMPOSE


def test_lite_issuer_is_available_to_embedded_backend_mode_selection():
    blockchain = _service_block("blockchain-services")

    assert "- ISSUER=${ISSUER:-}" in blockchain
    assert 'mode="$${BLOCKCHAIN_SERVICES_ENABLED:-auto}"' in blockchain
    assert 'issuer="$${ISSUER:-}"' in blockchain
    assert 'local_issuer="https://$${server_name}"' in blockchain
    assert 'Embedded blockchain-services disabled (Lite mode)' in blockchain
