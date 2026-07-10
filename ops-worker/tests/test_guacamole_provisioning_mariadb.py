import os
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def test_temporary_guacamole_user_activates_on_mariadb():
    database_url = os.getenv("GUACAMOLE_MARIADB_TEST_URL")
    if not database_url:
        pytest.skip("GUACAMOLE_MARIADB_TEST_URL is not configured")

    engine = create_engine(database_url, future=True)
    original_engine = worker.GUACAMOLE_DB_ENGINE
    worker.GUACAMOLE_DB_ENGINE = engine
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS guacamole_connection_permission"))
            conn.execute(text("DROP TABLE IF EXISTS guacamole_user"))
            conn.execute(text("DROP TABLE IF EXISTS guacamole_entity"))
            conn.execute(text("DROP TABLE IF EXISTS guacamole_connection_parameter"))
            conn.execute(text("DROP TABLE IF EXISTS guacamole_connection"))
            conn.execute(text("""
                CREATE TABLE guacamole_connection (
                    connection_id INT NOT NULL PRIMARY KEY,
                    connection_name VARCHAR(128) NOT NULL,
                    protocol VARCHAR(32) NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE guacamole_connection_parameter (
                    connection_id INT NOT NULL,
                    parameter_name VARCHAR(128) NOT NULL,
                    parameter_value VARCHAR(4096) NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE guacamole_entity (
                    entity_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    type VARCHAR(16) NOT NULL,
                    UNIQUE KEY uk_guacamole_entity_name_type (name, type)
                )
            """))
            conn.execute(text("""
                CREATE TABLE guacamole_user (
                    entity_id INT NOT NULL PRIMARY KEY,
                    password_hash BINARY(32) NOT NULL,
                    password_date DATETIME NOT NULL,
                    disabled BOOLEAN NOT NULL,
                    expired BOOLEAN NOT NULL,
                    valid_until DATE NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE guacamole_connection_permission (
                    entity_id INT NOT NULL,
                    connection_id INT NOT NULL,
                    permission VARCHAR(16) NOT NULL,
                    PRIMARY KEY (entity_id, connection_id, permission)
                )
            """))
            conn.execute(text("""
                INSERT INTO guacamole_connection (connection_id, connection_name, protocol)
                VALUES (42, 'MariaDB RDP Lab', 'rdp')
            """))
            conn.execute(text("""
                INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
                VALUES (42, 'hostname', 'lab-ws-42'), (42, 'port', '3389')
            """))

        result = worker.provision_guacamole_temporary_user(
            "guac:id:42",
            "mariadb-session",
            int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()),
            activate=True,
        )

        assert result["username"] == "dlabs-res-mariadb-session"
        with engine.begin() as conn:
            permission_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM guacamole_connection_permission cp
                JOIN guacamole_entity e ON e.entity_id = cp.entity_id
                WHERE e.name = 'dlabs-res-mariadb-session'
                  AND cp.connection_id = 42
                  AND cp.permission = 'READ'
            """)).scalar_one()
        assert permission_count == 1
    finally:
        worker.GUACAMOLE_DB_ENGINE = original_engine
        engine.dispose()
