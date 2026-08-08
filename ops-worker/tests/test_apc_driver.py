import io
import os
import json
import sys

import pytest
from cryptography.fernet import Fernet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.apc_snmp import (
    APC_LEGACY_OIDS,
    APC_RPDU2_OIDS,
    ApcPowerNetSnmpDriver,
)
from power.drivers.base import PowerDriverError
from power.credentials import PowerCredentialError, PowerCredentialStore
import power_credentials
from power.models import PowerCapabilities, PowerController, PowerOutlet
from power.registry import PowerRegistry, RegisteredController
from power.service import PowerRuntime


class FakeSnmpClient:
    def __init__(self, values=None, walks=None):
        self.values = dict(values or {})
        self.walks = {key: list(value) for key, value in (walks or {}).items()}
        self.set_calls = []

    def get(self, oid):
        if oid not in self.values:
            raise PowerDriverError(f"missing fake OID {oid}")
        return self.values[oid]

    def set(self, oid, value):
        self.set_calls.append((oid, value))
        self.values[oid] = value
        return value

    def walk(self, oid):
        if oid not in self.walks:
            raise PowerDriverError(f"missing fake walk {oid}")
        return list(self.walks[oid])


class UnreachablePowerDriver:
    capabilities = PowerCapabilities(per_outlet_switching=True, read_back_state=True)

    def list_outlets(self):
        raise PowerDriverError("timeout")

    def discover(self):
        return {"reachable": False, "errorCode": "TIMEOUT"}


def test_apc_legacy_discovers_model_firmware_and_outlet_states():
    values = {
        APC_LEGACY_OIDS["model"]: "AP7920B",
        APC_LEGACY_OIDS["firmware"]: "v3.9.4",
        APC_LEGACY_OIDS["outlet_count"]: 2,
        APC_LEGACY_OIDS["state"] + ".1": 1,
        APC_LEGACY_OIDS["state"] + ".2": 2,
        APC_LEGACY_OIDS["name"] + ".1": "PLC",
        APC_LEGACY_OIDS["name"] + ".2": "HMI",
    }
    driver = ApcPowerNetSnmpDriver(
        "pdu-1",
        "192.0.2.20",
        config={"profile": "legacy"},
        credentials={"version": "v2c", "community": "test"},
        client=FakeSnmpClient(values),
    )

    discovered = driver.discover()
    outlets = driver.list_outlets()

    assert discovered == {
        "reachable": True,
        "driver": "apc-powernet-snmp",
        "controllerId": "pdu-1",
        "profile": "legacy",
        "model": "AP7920B",
        "firmware": "v3.9.4",
        "outletCount": 2,
    }
    assert outlets == [
        {"outlet": "1", "name": "PLC", "state": "on"},
        {"outlet": "2", "name": "HMI", "state": "off"},
    ]


def test_apc_legacy_commands_use_powernet_values_and_read_back():
    state_oid = APC_LEGACY_OIDS["state"] + ".1"
    client = FakeSnmpClient({state_oid: 2})
    driver = ApcPowerNetSnmpDriver(
        "pdu-1",
        "192.0.2.20",
        config={"profile": "legacy"},
        credentials={"version": "v1", "community": "test"},
        client=client,
    )

    on = driver.set_outlet_state("1", "on")
    cycle = driver.cycle_outlet("1", off_seconds=1)

    assert client.set_calls == [(state_oid, 1), (state_oid, 3)]
    assert on == {"outlet": "1", "state": "on", "success": True}
    assert cycle == {"outlet": "1", "state": "on", "success": True}


def test_apc_rpdu2_discovers_outlets_from_status_table():
    status = APC_RPDU2_OIDS
    client = FakeSnmpClient(
        walks={
            status["index"]: [(status["index"] + ".1", 1), (status["index"] + ".2", 2)],
            status["name"]: [(status["name"] + ".1", "PLC"), (status["name"] + ".2", "HMI")],
            status["number"]: [(status["number"] + ".1", 1), (status["number"] + ".2", 2)],
            status["state"]: [(status["state"] + ".1", 2), (status["state"] + ".2", 1)],
        }
    )
    driver = ApcPowerNetSnmpDriver(
        "pdu-2",
        "192.0.2.21",
        config={"profile": "rpdu2"},
        credentials={"version": "v3", "username": "power"},
        client=client,
    )

    outlets = driver.list_outlets()

    assert outlets == [
        {"outlet": "1", "name": "PLC", "state": "on"},
        {"outlet": "2", "name": "HMI", "state": "off"},
    ]


def test_apc_driver_rejects_missing_snmp_credentials():
    with pytest.raises(PowerDriverError, match="SNMP credentials"):
        ApcPowerNetSnmpDriver(
            "pdu-1",
            "192.0.2.20",
            config={"profile": "legacy"},
            credentials={},
            client=FakeSnmpClient(),
        )


def test_apc_driver_rejects_unknown_outlet_state():
    state_oid = APC_LEGACY_OIDS["state"] + ".1"
    driver = ApcPowerNetSnmpDriver(
        "pdu-1",
        "192.0.2.20",
        config={"profile": "legacy"},
        credentials={"version": "v2c", "community": "test"},
        client=FakeSnmpClient({state_oid: 4}),
    )

    with pytest.raises(PowerDriverError, match="unknown outlet state"):
        driver.get_outlet_state("1")


def test_power_credentials_are_resolved_from_encrypted_reference(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    encrypted = Fernet(key).encrypt(
        json.dumps({"version": "v2c", "community": "private"}).encode("utf-8")
    ).decode("ascii")
    credential_path = tmp_path / "power-credentials.json"
    credential_path.write_text(
        json.dumps({"credentials": {"pdu-1": {"type": "snmpv2c", "token": encrypted}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPS_POWER_CREDENTIALS_PATH", str(credential_path))
    monkeypatch.setenv("OPS_SECRETS_KEY", key.decode("ascii"))

    credentials = PowerCredentialStore.from_environment().get("PDU-1")

    assert credentials == {"version": "v2c", "community": "private"}


def test_invalid_power_credential_key_fails_only_when_resolving(tmp_path):
    store = PowerCredentialStore(str(tmp_path / "missing.json"), "not-a-fernet-key")

    with pytest.raises(PowerCredentialError, match="key is invalid"):
        store.get("pdu-1")


def test_power_credentials_can_be_provisioned_without_exposing_token(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    store = PowerCredentialStore(str(tmp_path / "power-credentials.json"), key)

    stored = store.put(
        "PDU-1",
        "snmpv2c",
        {"version": "v2c", "community": "private"},
    )

    assert stored == {"credentialRef": "pdu-1", "type": "snmpv2c"}
    assert store.get("pdu-1") == {"version": "v2c", "community": "private"}
    assert store.list() == [{"credentialRef": "pdu-1", "type": "snmpv2c"}]
    assert "private" not in (tmp_path / "power-credentials.json").read_text(encoding="utf-8")


def test_power_credentials_cli_reads_secret_from_stdin_and_prints_metadata(
    tmp_path, monkeypatch, capsys
):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("OPS_POWER_CREDENTIALS_PATH", str(tmp_path / "power-credentials.json"))
    monkeypatch.setenv("OPS_SECRETS_KEY", key)
    monkeypatch.setattr(
        power_credentials.sys,
        "stdin",
        io.StringIO('{"version":"v2c","community":"private"}'),
    )

    assert power_credentials.main(
        ["set", "--ref", "pdu-1", "--type", "snmpv2c"]
    ) == 0
    output = capsys.readouterr()

    assert json.loads(output.out) == {"credentialRef": "pdu-1", "type": "snmpv2c"}
    assert "private" not in output.out
    assert "private" not in (tmp_path / "power-credentials.json").read_text(encoding="utf-8")

    monkeypatch.setattr(power_credentials.sys, "stdin", io.StringIO(""))
    assert power_credentials.main(["list"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"credentialRef": "pdu-1", "type": "snmpv2c"}
    ]


def test_registry_builds_apc_driver_from_credential_reference():
    registry = PowerRegistry.from_config(
        {
            "controllers": [
                {
                    "id": "pdu-1",
                    "name": "APC test PDU",
                    "driver": "apc-powernet-snmp",
                    "host": "192.0.2.20",
                    "credentialRef": "pdu-1-snmp",
                    "config": {"profile": "legacy", "snmpVersion": "v2c"},
                }
            ],
            "outlets": [{"controllerId": "pdu-1", "outlet": "1"}],
        },
        credential_resolver=lambda reference: {
            "version": "v2c",
            "community": "private",
        },
    )

    assert registry.get("pdu-1").driver.__class__.__name__ == "ApcPowerNetSnmpDriver"


def test_power_runtime_from_path_passes_apc_credential_resolver(tmp_path):
    config_path = tmp_path / "power-controllers.json"
    config_path.write_text(
        json.dumps(
            {
                "controllers": [
                    {
                        "id": "pdu-1",
                        "name": "APC test PDU",
                        "driver": "apc-powernet-snmp",
                        "host": "192.0.2.20",
                        "credentialRef": "pdu-1-snmp",
                        "config": {"profile": "legacy"},
                    }
                ],
                "outlets": [{"controllerId": "pdu-1", "outlet": "1"}],
                "policies": [],
            }
        ),
        encoding="utf-8",
    )

    runtime = PowerRuntime.from_path(
        str(config_path),
        credential_resolver=lambda reference: {
            "version": "v2c",
            "community": "private",
        },
    )

    assert runtime.registry.get("pdu-1").driver.__class__.__name__ == "ApcPowerNetSnmpDriver"


def test_registry_public_description_degrades_when_controller_is_unreachable():
    controller = RegisteredController(
        PowerController("pdu-1", "APC test PDU", "apc-powernet-snmp"),
        UnreachablePowerDriver(),
        {"1": PowerOutlet("pdu-1", "1")},
    )

    description = PowerRegistry([controller]).public_description(controller)

    assert description["discovery"] == {"reachable": False, "errorCode": "TIMEOUT"}
    assert description["outlets"][0]["state"] == "unknown"
