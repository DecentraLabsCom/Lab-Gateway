import json
import os
import sys
import tempfile
from unittest.mock import patch

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.engine import Engine

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


def guacamole_engine() -> Engine:
    engine = worker.GUACAMOLE_DB_ENGINE
    assert engine is not None
    return engine


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
        "guacamole_user",
        metadata,
        Column("entity_id", Integer, primary_key=True),
        Column("valid_until", DateTime, nullable=True),
        Column("disabled", Boolean, nullable=False, server_default=text("0")),
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
        "users": ["demo", "alice", "dlabs-res-session"],
    }]

    with with_inventory_state(hosts, guacamole):
        response = client.get("/api/hosts")

    assert response.status_code == 200
    body = response.get_json()
    assert body["hosts"][0]["name"] == "lab-ws-01"
    assert body["hosts"][0]["guacamole"]["status"] == "linked"
    assert body["hosts"][0]["guacamole"]["connections"][0]["name"] == "RDP Lab 01"
    assert body["hosts"][0]["guacamole"]["connections"][0]["selector"] == "guac:id:7"
    assert body["hosts"][0]["guacamole"]["connections"][0]["hostname"] == "lab-ws-01"
    assert body["hosts"][0]["guacamole"]["connections"][0]["users"] == ["demo", "alice"]
    assert body["guacamoleUnmatched"] == []


def test_cleanup_expired_guacamole_temp_users_removes_only_expired_temp_entities():
    with with_inventory_state([], []):
        with guacamole_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO guacamole_entity (entity_id, name, type) "
                    "VALUES (1, 'dlabs-res-expired', 'USER'), "
                    "(2, 'dlabs-res-live', 'USER'), "
                    "(3, 'alice', 'USER')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO guacamole_user (entity_id, valid_until) "
                    "VALUES (1, date('now', '-1 day')), "
                    "(2, date('now')), "
                    "(3, date('now', '-1 day'))"
                )
            )

        deleted = worker.cleanup_expired_guacamole_temp_users()

        with guacamole_engine().begin() as conn:
            names = [
                row[0]
                for row in conn.execute(
                    text("SELECT name FROM guacamole_entity ORDER BY entity_id")
                ).all()
            ]
        assert deleted == 1
        assert names == ["dlabs-res-live", "alice"]


def test_internal_guacamole_provision_creates_temp_user(client):
    guacamole = [{
        "id": 42,
        "name": "RDP Lab 42",
        "protocol": "rdp",
        "hostname": "lab-ws-42",
        "port": "3389",
    }]

    with with_inventory_state([], guacamole):
        response = client.post(
            "/internal/guacamole/provision",
            json={
                "selector": "guac:id:42",
                "sessionId": "session-42",
                "validUntilEpochSeconds": 1800000000,
            },
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["username"] == "dlabs-res-session-42"
        assert body["connection"]["selector"] == "guac:id:42"

        with guacamole_engine().begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT e.name, cp.connection_id, cp.permission
                    FROM guacamole_entity e
                    JOIN guacamole_connection_permission cp ON cp.entity_id = e.entity_id
                    WHERE e.name = 'dlabs-res-session-42'
                    """
                )
            ).mappings().all()
        assert rows[0]["connection_id"] == 42
        assert rows[0]["permission"] == "READ"


def test_internal_guacamole_provision_can_stage_and_then_activate_temp_user(client):
    guacamole = [{"id": 42, "name": "RDP Lab 42", "protocol": "rdp", "hostname": "lab-ws-42", "port": "3389"}]
    with with_inventory_state([], guacamole):
        staged = client.post(
            "/internal/guacamole/provision",
            json={"selector": "guac:id:42", "sessionId": "session-staged", "validUntilEpochSeconds": 1800000000, "activate": False},
        )
        assert staged.status_code == 200
        with guacamole_engine().begin() as conn:
            entity_id = conn.execute(text("SELECT entity_id FROM guacamole_entity WHERE name = 'dlabs-res-session-staged'")) .scalar()
            assert conn.execute(text("SELECT disabled FROM guacamole_user WHERE entity_id = :entity_id"), {"entity_id": entity_id}).scalar() == 1
            assert conn.execute(text("SELECT COUNT(*) FROM guacamole_connection_permission WHERE entity_id = :entity_id"), {"entity_id": entity_id}).scalar() == 0

        activated = client.post(
            "/internal/guacamole/provision",
            json={"selector": "guac:id:42", "sessionId": "session-staged", "validUntilEpochSeconds": 1800000000, "activate": True},
        )
        assert activated.status_code == 200
        with guacamole_engine().begin() as conn:
            assert conn.execute(text("SELECT disabled FROM guacamole_user WHERE entity_id = :entity_id"), {"entity_id": entity_id}).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM guacamole_connection_permission WHERE entity_id = :entity_id"), {"entity_id": entity_id}).scalar() == 1


def test_internal_guacamole_provision_rejects_non_boolean_activate(client):
    with with_inventory_state([], [{"id": 42, "name": "RDP Lab 42", "protocol": "rdp", "hostname": "lab-ws-42", "port": "3389"}]):
        response = client.post(
            "/internal/guacamole/provision",
            json={"selector": "guac:id:42", "sessionId": "session-invalid-activate", "validUntilEpochSeconds": 1800000000, "activate": "false"},
        )

    assert response.status_code == 400
    assert response.get_json()["error"] == "activate must be a boolean"


def test_internal_guacamole_delete_removes_temp_user(client):
    guacamole = [{"id": 42, "name": "RDP Lab 42", "protocol": "rdp", "hostname": "lab-ws-42", "port": "3389"}]
    with with_inventory_state([], guacamole):
        provision = client.post(
            "/internal/guacamole/provision",
            json={"selector": "guac:id:42", "sessionId": "session-delete", "validUntilEpochSeconds": 1800000000},
        )
        assert provision.status_code == 200
        deleted = client.delete("/internal/guacamole/provision/session-delete")
        assert deleted.status_code == 200
        assert deleted.get_json()["deleted"] is True
        with guacamole_engine().begin() as conn:
            remaining = conn.execute(text("SELECT COUNT(*) FROM guacamole_entity WHERE name = 'dlabs-res-session-delete'"))
            assert remaining.scalar() == 0



def test_internal_guacamole_provision_requires_token_when_configured(client):
    original = worker.GUACAMOLE_PROVISIONER_TOKEN
    try:
        worker.GUACAMOLE_PROVISIONER_TOKEN = "secret"
        with with_inventory_state([], []):
            unauthorized = client.get("/internal/guacamole/connections")
            authorized = client.get(
                "/internal/guacamole/connections",
                headers={"X-Guacamole-Provisioner-Token": "secret"},
            )
        assert unauthorized.status_code == 401
        assert authorized.status_code == 200
    finally:
        worker.GUACAMOLE_PROVISIONER_TOKEN = original


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


def test_discover_suggests_mac_from_heartbeat_when_winrm_reachable(client, monkeypatch):
    guacamole = [{
        "id": 16,
        "name": "Lab Station With Telemetry",
        "protocol": "rdp",
        "hostname": "lab-telemetry",
        "port": "3389",
    }]
    heartbeat = {
        "status": {
            "wake": {
                "nicPower": [
                    {
                        "name": "Wi-Fi",
                        "macAddress": "AA-BB-CC-DD-EE-FF",
                        "status": "Up",
                        "wolReady": False,
                    },
                    {
                        "name": "Ethernet",
                        "macAddress": "00-11-22-33-44-55",
                        "status": "Up",
                        "wolReady": True,
                    },
                ]
            }
        }
    }
    monkeypatch.setenv("WINRM_USER_LAB_TELEMETRY", "ops-user")
    monkeypatch.setenv("WINRM_PASS_LAB_TELEMETRY", "ops-pass")

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", side_effect=lambda host, port, timeout=None: port == 5985), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": False,
                "status": "no-response",
            }), \
            patch("worker.read_remote_file", return_value=json.dumps(heartbeat)):
        response = client.post("/api/hosts/discover", json={"connectionId": 16})

    assert response.status_code == 200
    body = response.get_json()
    assert body["opsHostDraft"]["mac"] == "00:11:22:33:44:55"
    assert body["checks"]["heartbeat"]["detected"] is True
    assert body["checks"]["heartbeat"]["suggestedMac"]["source"] == "status.wake.nicPower"


def test_discover_uses_first_readable_heartbeat_path(client, monkeypatch):
    guacamole = [{
        "id": 19,
        "name": "Lab Station Custom Path",
        "protocol": "rdp",
        "hostname": "lab-custom-path",
        "port": "3389",
    }]
    monkeypatch.setenv("WINRM_USER_LAB_CUSTOM_PATH", "ops-user")
    monkeypatch.setenv("WINRM_PASS_LAB_CUSTOM_PATH", "ops-pass")
    monkeypatch.setattr(worker, "DISCOVERY_HEARTBEAT_PATHS", [
        r"C:\Missing\heartbeat.json",
        r"D:\LabStation\data\heartbeat.json",
    ])

    def fake_read_remote_file(_host, path, *_args):
        if path == r"D:\LabStation\data\heartbeat.json":
            return json.dumps({"status": {"wake": {"nicPower": []}}})
        raise RuntimeError("missing")

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", side_effect=lambda host, port, timeout=None: port == 5985), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": False,
                "status": "no-response",
            }), \
            patch("worker.read_remote_file", side_effect=fake_read_remote_file):
        response = client.post("/api/hosts/discover", json={"connectionId": 19})

    assert response.status_code == 200
    body = response.get_json()
    assert body["checks"]["heartbeat"]["path"] == r"D:\LabStation\data\heartbeat.json"
    assert body["opsHostDraft"]["heartbeat_path"] == r"D:\LabStation\data\heartbeat.json"


def test_discover_derives_heartbeat_path_from_scheduled_task(client, monkeypatch):
    guacamole = [{
        "id": 23,
        "name": "Installed Lab Station",
        "protocol": "rdp",
        "hostname": "lab-installed",
        "port": "3389",
    }]
    monkeypatch.setenv("WINRM_USER_LAB_INSTALLED", "ops-user")
    monkeypatch.setenv("WINRM_PASS_LAB_INSTALLED", "ops-pass")
    derived_path = r"C:\Users\operator\Downloads\LabStation\labstation\data\telemetry\heartbeat.json"

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", side_effect=lambda host, port, timeout=None: port == 5985), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": False,
                "status": "no-response",
            }), \
            patch("worker.query_labstation_task_heartbeat_path", return_value=derived_path), \
            patch("worker.read_remote_file", return_value=json.dumps({"status": {"wake": {"nicPower": []}}})):
        response = client.post("/api/hosts/discover", json={"connectionId": 23})

    assert response.status_code == 200
    body = response.get_json()
    assert body["checks"]["heartbeat"]["path"] == derived_path
    assert body["opsHostDraft"]["heartbeat_path"] == derived_path


def test_discover_suggests_names_from_guacamole_connections_with_same_host(client):
    guacamole = [
        {
            "id": 20,
            "name": "Physics Bench A",
            "protocol": "rdp",
            "hostname": "10.7.74.10",
            "port": "3389",
        },
        {
            "id": 21,
            "name": "Physics Bench A Admin",
            "protocol": "rdp",
            "hostname": "10.7.74.10",
            "port": "3390",
        },
        {
            "id": 22,
            "name": "Other Bench",
            "protocol": "rdp",
            "hostname": "10.7.74.11",
            "port": "3389",
        },
    ]

    with with_inventory_state([], guacamole), \
            patch("worker.tcp_port_open", return_value=False), \
            patch("worker.probe_labstation_http", return_value={
                "checked": True,
                "detected": False,
                "status": "no-response",
            }):
        response = client.post("/api/hosts/discover", json={"connectionId": 20})

    assert response.status_code == 200
    body = response.get_json()
    assert body["opsHostDraft"]["nameCandidates"] == ["Physics Bench A", "Physics Bench A Admin", "10.7.74.10"]


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


def test_provision_writes_dynamic_host_with_credential_ref_and_reloads(client):
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
        })
        with open(state.dynamic_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)

    assert response.status_code == 200
    assert response.get_json()["host"]["name"] == "lab-ws-14"
    saved_host = saved["hosts"][0]
    assert saved_host["credential_ref"] == "lab-ws-14"
    assert saved_host["mac"] == "00:11:22:33:44:55"
    assert saved_host["labs"] == ["14"]


def test_provision_rejects_lab_not_in_candidate_allowlist(client):
    guacamole = [{
        "id": 18,
        "name": "Provisionable With Lab Candidates",
        "protocol": "rdp",
        "hostname": "lab-ws-18",
        "port": "3389",
    }]

    with with_dynamic_inventory_state([], guacamole), \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "labstation-detected",
                "checks": {},
            }):
        response = client.post("/api/hosts/provision", json={
            "connectionId": 18,
            "name": "lab-ws-18",
            "labs": ["99"],
            "validLabIds": ["18"],
            "winrmUserEnv": "WINRM_USER_LAB_WS_18",
            "winrmPassEnv": "WINRM_PASS_LAB_WS_18",
        })

    assert response.status_code == 400
    assert "not valid candidates" in response.get_data(as_text=True)


def test_provision_uses_discovered_mac_when_payload_mac_blank(client):
    guacamole = [{
        "id": 17,
        "name": "Provisionable With Suggested MAC",
        "protocol": "rdp",
        "hostname": "lab-ws-17",
        "port": "3389",
    }]

    with with_dynamic_inventory_state([], guacamole) as state, \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "labstation-detected",
                "checks": {},
                "opsHostDraft": {"mac": "00:11:22:33:44:55"},
            }):
        response = client.post("/api/hosts/provision", json={
            "connectionId": 17,
            "name": "lab-ws-17",
            "mac": "",
            "labs": ["17"],
            "winrmUserEnv": "WINRM_USER_LAB_WS_17",
            "winrmPassEnv": "WINRM_PASS_LAB_WS_17",
        })
        with open(state.dynamic_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)

    assert response.status_code == 200
    assert saved["hosts"][0]["mac"] == "00:11:22:33:44:55"


def test_save_winrm_credentials_stores_secret_and_reloads(client, monkeypatch, tmp_path):
    guacamole = [{
        "id": 15,
        "name": "Credential Host",
        "protocol": "rdp",
        "hostname": "lab-ws-15",
        "port": "3389",
    }]
    monkeypatch.setattr(worker, "OPS_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))
    monkeypatch.setattr(worker, "OPS_SECRETS_KEY_PATH", str(tmp_path / "secrets.key"))
    monkeypatch.setattr(worker, "_FERNET", None)

    with with_dynamic_inventory_state([], guacamole) as state, \
            patch("worker.discover_labstation_candidate", return_value={
                "connection": guacamole[0],
                "status": "winrm-reachable",
                "checks": {},
            }):
        provision_response = client.post("/api/hosts/provision", json={
            "connectionId": 15,
        })
        credentials_response = client.post("/api/hosts/winrm-credentials", json={
            "credentialRef": "lab-ws-15",
            "user": ".\\LabGatewaySvc",
            "password": "secret-password",
        })
        with open(state.dynamic_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)

    assert provision_response.status_code == 200
    assert credentials_response.status_code == 200
    assert saved["hosts"][0]["credential_ref"] == "lab-ws-15"
    creds = worker.load_winrm_credentials("lab-ws-15")
    assert creds == {"user": ".\\LabGatewaySvc", "password": "secret-password"}
