import json
import os
import sys
import tempfile
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def make_guacamole_engine(rows):
    engine = create_engine("sqlite:///:memory:", future=True)
    metadata = MetaData()
    Table(
        "guacamole_connection",
        metadata,
        Column("connection_id", Integer, primary_key=True),
        Column("connection_name", String(128), nullable=False),
        Column("protocol", String(32), nullable=False),
    )
    Table(
        "guacamole_connection_parameter",
        metadata,
        Column("connection_id", Integer, nullable=False),
        Column("parameter_name", String(128), nullable=False),
        Column("parameter_value", String(4096), nullable=False),
    )
    Table(
        "guacamole_entity",
        metadata,
        Column("entity_id", Integer, primary_key=True),
        Column("name", String(128), nullable=False),
        Column("type", String(16), nullable=False),
    )
    Table(
        "guacamole_connection_permission",
        metadata,
        Column("entity_id", Integer, nullable=False),
        Column("connection_id", Integer, nullable=False),
        Column("permission", String(16), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        entity_id = 1
        for row in rows:
            conn.execute(
                text(
                    "INSERT INTO guacamole_connection "
                    "(connection_id, connection_name, protocol) "
                    "VALUES (:id, :name, :protocol)"
                ),
                {
                    "id": row["id"],
                    "name": row["name"],
                    "protocol": row.get("protocol", "rdp"),
                },
            )
            for key in ("hostname", "port"):
                if row.get(key):
                    conn.execute(
                        text(
                            "INSERT INTO guacamole_connection_parameter "
                            "(connection_id, parameter_name, parameter_value) "
                            "VALUES (:id, :name, :value)"
                        ),
                        {"id": row["id"], "name": key, "value": row[key]},
                    )
            for username in row.get("users", []):
                conn.execute(
                    text(
                        "INSERT INTO guacamole_entity "
                        "(entity_id, name, type) "
                        "VALUES (:entity_id, :name, 'USER')"
                    ),
                    {"entity_id": entity_id, "name": username},
                )
                conn.execute(
                    text(
                        "INSERT INTO guacamole_connection_permission "
                        "(entity_id, connection_id, permission) "
                        "VALUES (:entity_id, :connection_id, 'READ')"
                    ),
                    {"entity_id": entity_id, "connection_id": row["id"]},
                )
                entity_id += 1
    return engine


def with_inventory_state(hosts, guacamole_rows):
    class InventoryState:
        def __enter__(self):
            self.original_hosts = worker.HOSTS
            self.original_guacamole_engine = worker.GUACAMOLE_DB_ENGINE
            worker.HOSTS = worker.HostRegistry({"hosts": hosts})
            worker.GUACAMOLE_DB_ENGINE = make_guacamole_engine(guacamole_rows)

        def __exit__(self, exc_type, exc, tb):
            worker.HOSTS = self.original_hosts
            worker.GUACAMOLE_DB_ENGINE = self.original_guacamole_engine

    return InventoryState()


def with_dynamic_inventory_state(hosts, guacamole_rows):
    class DynamicInventoryState:
        def __enter__(self):
            self.tmpdir = tempfile.TemporaryDirectory()
            self.base_path = os.path.join(self.tmpdir.name, "base-hosts.json")
            self.dynamic_path = os.path.join(self.tmpdir.name, "hosts.json")
            self.original_hosts = worker.HOSTS
            self.original_guacamole_engine = worker.GUACAMOLE_DB_ENGINE
            self.original_base_config_path = worker.CONFIG_PATH
            self.original_config_path = worker.DYNAMIC_CONFIG_PATH
            with open(self.base_path, "w", encoding="utf-8") as handle:
                json.dump({"hosts": hosts}, handle)
            worker.HOSTS = worker.HostRegistry({"hosts": hosts})
            worker.GUACAMOLE_DB_ENGINE = make_guacamole_engine(guacamole_rows)
            worker.CONFIG_PATH = self.base_path
            worker.DYNAMIC_CONFIG_PATH = self.dynamic_path
            return self

        def __exit__(self, exc_type, exc, tb):
            worker.HOSTS = self.original_hosts
            worker.GUACAMOLE_DB_ENGINE = self.original_guacamole_engine
            worker.CONFIG_PATH = self.original_base_config_path
            worker.DYNAMIC_CONFIG_PATH = self.original_config_path
            self.tmpdir.cleanup()

    return DynamicInventoryState()


def test_host_inventory_links_guacamole_connection_by_hostname(client):
    hosts = [{
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "mac": "00:11:22:33:44:55",
        "labs": ["1"],
        "winrm_user": "user",
        "winrm_pass": "pass",
    }]
    guacamole = [{
        "id": 7,
        "name": "RDP Lab 01",
        "protocol": "rdp",
        "hostname": "lab-ws-01",
        "port": "3389",
        "users": ["demo", "alice"],
    }]

    with with_inventory_state(hosts, guacamole):
        response = client.get("/api/hosts")

    assert response.status_code == 200
    body = response.get_json()
    assert body["hosts"][0]["name"] == "lab-ws-01"
    assert body["hosts"][0]["guacamole"]["status"] == "linked"
    assert body["hosts"][0]["guacamole"]["connections"][0]["name"] == "RDP Lab 01"
    assert body["hosts"][0]["guacamole"]["connections"][0]["hostname"] == "lab-ws-01"
    assert body["hosts"][0]["guacamole"]["connections"][0]["users"] == ["demo", "alice"]
    assert body["guacamoleUnmatched"] == []


def test_host_inventory_marks_missing_when_no_connection_matches(client):
    hosts = [{
        "name": "lab-ws-02",
        "address": "192.168.1.51",
        "winrm_user": "user",
        "winrm_pass": "pass",
    }]
    guacamole = [{
        "id": 8,
        "name": "Other Desktop",
        "protocol": "rdp",
        "hostname": "other-host",
        "port": "3389",
    }]

    with with_inventory_state(hosts, guacamole):
        response = client.get("/api/hosts")

    assert response.status_code == 200
    body = response.get_json()
    assert body["hosts"][0]["guacamole"]["status"] == "missing"
    assert body["hosts"][0]["guacamole"]["connections"] == []
    assert body["guacamoleUnmatched"][0]["name"] == "Other Desktop"


def test_host_inventory_marks_ambiguous_when_multiple_connections_match(client):
    hosts = [{
        "name": "lab-ws-03",
        "address": "192.168.1.52",
        "winrm_user": "user",
        "winrm_pass": "pass",
    }]
    guacamole = [
        {
            "id": 9,
            "name": "Primary RDP",
            "protocol": "rdp",
            "hostname": "lab-ws-03",
            "port": "3389",
        },
        {
            "id": 10,
            "name": "Backup RDP",
            "protocol": "rdp",
            "hostname": "192.168.1.52",
            "port": "3390",
        },
    ]

    with with_inventory_state(hosts, guacamole):
        response = client.get("/api/hosts")

    assert response.status_code == 200
    guacamole_status = response.get_json()["hosts"][0]["guacamole"]
    assert guacamole_status["status"] == "ambiguous"
    assert [conn["name"] for conn in guacamole_status["connections"]] == ["Primary RDP", "Backup RDP"]


def test_discover_requires_connection_id(client):
    response = client.post("/api/hosts/discover", json={})

    assert response.status_code == 400
    assert "connectionId is required" in response.get_data(as_text=True)


def test_discover_returns_404_for_unknown_connection(client):
    with with_inventory_state([], []):
        response = client.post("/api/hosts/discover", json={"connectionId": 999})

    assert response.status_code == 404
    assert "not found" in response.get_data(as_text=True)


def test_discover_detects_labstation_http_service(client):
    guacamole = [{
        "id": 11,
        "name": "Lab Station Candidate",
        "protocol": "rdp",
        "hostname": "lab-candidate",
        "port": "3389",
    }]

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", side_effect=lambda host, port, timeout=None: port == 5985), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": True,
                "url": "http://lab-candidate:8765/labstation/health",
                "statusCode": 200,
                "service": "LabStation",
            }):
        response = client.post("/api/hosts/discover", json={"connectionId": 11})

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "labstation-detected"
    assert body["connection"]["hostname"] == "lab-candidate"
    assert body["checks"]["winrm"]["5985"] is True
    assert body["checks"]["labStationHttp"]["detected"] is True


def test_discover_reports_winrm_reachable_when_no_labstation_http(client):
    guacamole = [{
        "id": 12,
        "name": "WinRM Candidate",
        "protocol": "rdp",
        "hostname": "winrm-only",
        "port": "3389",
    }]

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", side_effect=lambda host, port, timeout=None: port == 5986), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": False,
                "status": "no-response",
            }):
        response = client.post("/api/hosts/discover", json={"connectionId": 12})

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "winrm-reachable"
    assert body["checks"]["winrm"]["5986"] is True
    assert body["checks"]["labStationHttp"]["detected"] is False


def test_provision_rejects_candidate_without_labstation_or_winrm_signal(client):
    guacamole = [{
        "id": 13,
        "name": "Weak Candidate",
        "protocol": "rdp",
        "hostname": "weak-host",
        "port": "3389",
    }]

    with with_dynamic_inventory_state([], guacamole), \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "host-resolves",
                "checks": {},
            }):
        response = client.post("/api/hosts/provision", json={
            "connectionId": 13,
            "winrmUserEnv": "WINRM_USER_WEAK",
            "winrmPassEnv": "WINRM_PASS_WEAK",
        })

    assert response.status_code == 409
    assert "insufficient discovery signal" in response.get_data(as_text=True)


def test_provision_writes_dynamic_host_with_env_refs_and_reloads(client):
    guacamole = [{
        "id": 14,
        "name": "Provisionable",
        "protocol": "rdp",
        "hostname": "lab-ws-14",
        "port": "3389",
    }]

    with with_dynamic_inventory_state([], guacamole) as state, \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "labstation-detected",
                "checks": {},
            }):
        response = client.post("/api/hosts/provision", json={
            "connectionId": 14,
            "name": "lab-ws-14",
            "mac": "00:11:22:33:44:55",
            "labs": ["14"],
            "winrmUserEnv": "WINRM_USER_LAB_WS_14",
            "winrmPassEnv": "WINRM_PASS_LAB_WS_14",
        })
        with open(state.dynamic_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)

    assert response.status_code == 200
    assert response.get_json()["host"]["name"] == "lab-ws-14"
    saved_host = saved["hosts"][0]
    assert saved_host["winrm_user"] == "env:WINRM_USER_LAB_WS_14"
    assert saved_host["winrm_pass"] == "env:WINRM_PASS_LAB_WS_14"
    assert saved_host["mac"] == "00:11:22:33:44:55"
    assert saved_host["labs"] == ["14"]


def test_provision_rejects_raw_winrm_secret(client):
    guacamole = [{
        "id": 15,
        "name": "Bad Secret",
        "protocol": "rdp",
        "hostname": "lab-ws-15",
        "port": "3389",
    }]

    with with_dynamic_inventory_state([], guacamole), \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "winrm-reachable",
                "checks": {},
            }):
        response = client.post("/api/hosts/provision", json={
            "connectionId": 15,
            "winrmUserEnv": "Administrator",
            "winrmPassEnv": "plaintext-password",
        })

    assert response.status_code == 400
    assert "environment variable name" in response.get_data(as_text=True)
