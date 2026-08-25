import asyncio
import importlib
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.apc_snmp import (
    APC_LEGACY_OIDS,
    APC_RPDU2_OIDS,
    ApcPowerNetSnmpDriver,
    ApcSnmpError,
    _PySnmpClient,
)
from power.drivers.base import PowerDriverError


class MinimalSnmpClient:
    def __init__(self, values=None, walks=None, error=None):
        self.values = dict(values or {})
        self.walks = {key: list(value) for key, value in (walks or {}).items()}
        self.error = error

    def get(self, oid):
        if self.error:
            raise self.error
        if oid not in self.values:
            raise ApcSnmpError("OID_UNSUPPORTED")
        return self.values[oid]

    def set(self, oid, value):
        if self.error:
            raise self.error
        self.values[oid] = value
        return value

    def walk(self, oid):
        if self.error:
            raise self.error
        if oid not in self.walks:
            raise ApcSnmpError("OID_UNSUPPORTED")
        return list(self.walks[oid])


def build_driver(client, *, config=None, credentials=None):
    return ApcPowerNetSnmpDriver(
        "pdu-edge",
        "192.0.2.40",
        config=config or {"profile": "auto"},
        credentials=credentials or {"version": "v2c", "community": "private"},
        client=client,
    )


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("SNMP timeout", "TIMEOUT"),
        ("authorization denied", "AUTHENTICATION_FAILED"),
        ("unknown OID", "OID_UNSUPPORTED"),
        ("socket closed", "SNMP_REQUEST_FAILED"),
    ],
)
def test_apc_discover_sanitizes_client_failures(message, code):
    result = build_driver(MinimalSnmpClient(error=RuntimeError(message))).discover()

    assert result["reachable"] is False
    assert result["errorCode"] == code
    assert result["controllerId"] == "pdu-edge"


def test_apc_auto_profile_selects_rpdu2_and_uses_identity_fallback():
    client = MinimalSnmpClient(
        values={
            APC_RPDU2_OIDS["model"] + ".1": None,
            APC_RPDU2_OIDS["firmware"] + ".1": None,
            "1.3.6.1.2.1.1.1.0": "APC rPDU2 fallback",
        },
        walks={
            APC_RPDU2_OIDS["index"]: [(APC_RPDU2_OIDS["index"] + ".1", 1)],
            APC_RPDU2_OIDS["name"]: [(APC_RPDU2_OIDS["name"] + ".1", "PLC")],
            APC_RPDU2_OIDS["number"]: [(APC_RPDU2_OIDS["number"] + ".1", 1)],
            APC_RPDU2_OIDS["state"]: [(APC_RPDU2_OIDS["state"] + ".1", 2)],
        },
    )
    driver = build_driver(client)

    assert driver.discover() == {
        "reachable": True,
        "driver": "apc-powernet-snmp",
        "controllerId": "pdu-edge",
        "profile": "rpdu2",
        "model": "APC rPDU2 fallback",
        "firmware": None,
        "outletCount": 1,
    }


def test_apc_auto_profile_rejects_empty_rpdu2_table():
    client = MinimalSnmpClient(
        values={APC_LEGACY_OIDS["outlet_count"]: 0},
        walks={APC_RPDU2_OIDS["index"]: []},
    )

    result = build_driver(client).discover()

    assert result["reachable"] is False
    assert result["errorCode"] == "OID_UNSUPPORTED"


def test_apc_rpdu2_rejects_bad_rows_and_missing_state():
    client = MinimalSnmpClient(
        walks={
            APC_RPDU2_OIDS["index"]: [(APC_RPDU2_OIDS["index"] + ".1", 1)],
            APC_RPDU2_OIDS["name"]: [(APC_RPDU2_OIDS["name"] + ".1", "PLC")],
            APC_RPDU2_OIDS["number"]: [(APC_RPDU2_OIDS["number"] + ".1", 1)],
            APC_RPDU2_OIDS["state"]: [],
        }
    )
    driver = build_driver(client, config={"profile": "rpdu2"})

    with pytest.raises(ApcSnmpError, match="state is missing"):
        driver.list_outlets()

    client.walks[APC_RPDU2_OIDS["state"]] = [("1.2.3", 2)]
    with pytest.raises(ApcSnmpError, match="invalid table row"):
        driver.list_outlets()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host": "", "message": "host is required"},
        {"port": 0, "message": "port is invalid"},
        {"port": "invalid", "message": "port is invalid"},
        {"config": {"profile": "invalid"}, "message": "profile is invalid"},
        {"config": {"timeoutSeconds": 0}, "message": "must be positive"},
    ],
)
def test_apc_rejects_invalid_configuration(kwargs):
    message = kwargs.pop("message")
    client = None if "timeoutSeconds" in kwargs.get("config", {}) else MinimalSnmpClient()
    with pytest.raises(ApcSnmpError, match=message):
        ApcPowerNetSnmpDriver(
            "pdu-edge",
            kwargs.pop("host", "192.0.2.40"),
            port=kwargs.pop("port", 161),
            config=kwargs.pop("config", {"profile": "legacy"}),
            credentials={"version": "v2c", "community": "private"},
            client=client,
        )


def test_apc_rejects_invalid_commands_and_outlet_ids():
    driver = build_driver(MinimalSnmpClient(), config={"profile": "legacy"})

    with pytest.raises(PowerDriverError, match="state must be on or off"):
        driver.set_outlet_state("1", "toggle")
    with pytest.raises(PowerDriverError, match="positive integer"):
        driver.get_outlet_state("0")
    with pytest.raises(PowerDriverError, match="positive integer"):
        driver.set_outlet_state("x", "on")
    with pytest.raises(PowerDriverError, match="greater than zero"):
        driver.cycle_outlet("1", off_seconds=0)
    with pytest.raises(PowerDriverError, match="positive integer"):
        driver.cycle_outlet("x", off_seconds=1)


class FakePySnmpModule:
    usmNoAuthProtocol = "none-auth"
    usmHMACMD5AuthProtocol = "md5"
    usmHMACSHAAuthProtocol = "sha"
    usmHMAC128SHA224AuthProtocol = "sha224"
    usmHMAC192SHA256AuthProtocol = "sha256"
    usmHMAC256SHA384AuthProtocol = "sha384"
    usmHMAC384SHA512AuthProtocol = "sha512"
    usmNoPrivProtocol = "none-priv"
    usmDESPrivProtocol = "des"
    usmAesCfb128Protocol = "aes"
    response = (None, 0, 0, [("1.2.3", "value")])
    walk_response = [(None, 0, 0, [("1.2.3", "value")])]
    engines_closed = 0

    class SnmpEngine:
        def close_dispatcher(self):
            FakePySnmpModule.engines_closed += 1

    class UdpTransportTarget:
        @classmethod
        async def create(cls, address, timeout, retries):
            return cls()

    class CommunityData:
        def __init__(self, community, mpModel):
            self.community = community
            self.mpModel = mpModel

    class UsmUserData:
        def __init__(self, username, **kwargs):
            self.username = username
            self.options = kwargs

    class ContextData:
        pass

    class ObjectIdentity:
        def __init__(self, oid):
            self.oid = oid

    class ObjectType:
        def __init__(self, identity, value=None):
            self.identity = identity
            self.value = value

    class Integer:
        def __init__(self, value):
            self.value = value

    @staticmethod
    async def get_cmd(*_args):
        return FakePySnmpModule.response

    @staticmethod
    async def set_cmd(*_args):
        return FakePySnmpModule.response

    @staticmethod
    async def walk_cmd(*_args):
        for item in FakePySnmpModule.walk_response:
            yield item


def test_pysnmp_adapter_covers_auth_requests_walk_and_running_loop(monkeypatch):
    module = FakePySnmpModule
    monkeypatch.setattr(importlib, "import_module", lambda _name: module)
    client = _PySnmpClient(
        "192.0.2.41",
        161,
        {"version": "v3", "username": "monitor", "authProtocol": "SHA", "privProtocol": "AES"},
        timeout_seconds=2,
        retries=1,
    )

    assert client.get("1.2.3") == "value"
    assert client.set("1.2.3", 1) == "value"
    assert list(client.walk("1.2.3")) == [("1.2.3", "value")]
    assert module.engines_closed == 3

    async def call_inside_loop():
        return client._run(asyncio.sleep(0, result="inside-loop"))

    assert asyncio.run(call_inside_loop()) == "inside-loop"

    assert _PySnmpClient(
        "host", 161, {"version": "v1", "community": "public"}, timeout_seconds=1, retries=1
    )._auth(module).mpModel == 0
    assert _PySnmpClient(
        "host", 161, {"version": "v2c", "community": "public"}, timeout_seconds=1, retries=1
    )._auth(module).mpModel == 1


def test_pysnmp_adapter_translates_protocol_errors_and_empty_responses(monkeypatch):
    module = FakePySnmpModule
    monkeypatch.setattr(importlib, "import_module", lambda _name: module)
    client = _PySnmpClient(
        "host", 161, {"version": "v2c", "community": "public"}, timeout_seconds=1, retries=1
    )

    monkeypatch.setattr(module, "response", ("timeout", 0, 0, []))
    with pytest.raises(ApcSnmpError, match="operation failed") as error:
        client.get("1.2.3")
    assert error.value.error_code == "TIMEOUT"

    monkeypatch.setattr(module, "response", (None, 0, 0, []))
    with pytest.raises(ApcSnmpError, match="operation failed"):
        client.get("1.2.3")

    with pytest.raises(ApcSnmpError, match="security protocol"):
        _PySnmpClient(
            "host",
            161,
            {"version": "v3", "username": "user", "authProtocol": "invalid", "privProtocol": "NONE"},
            timeout_seconds=1,
            retries=1,
        )._auth(module)
