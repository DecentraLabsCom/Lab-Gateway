import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.base import PowerDriverError
from power.drivers.netio_json import NetioJsonDriver, NetioJsonError
from power.registry import PowerRegistry


def status_payload():
    return {
        "Agent": {"Model": "PowerPDU 4C", "Version": "3.1.0"},
        "Outputs": [
            {"ID": 1, "Name": "PLC", "State": 0, "Action": 6, "Load": 12.5},
            {"ID": 2, "Name": "HMI", "State": 1, "Action": 6, "Load": 0},
        ],
    }


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self):
        self.get_calls = []
        self.post_calls = []
        self.next_get = status_payload()
        self.next_post = status_payload()

    def get(self, url, *, auth, timeout, verify):
        self.get_calls.append({"url": url, "auth": auth, "timeout": timeout, "verify": verify})
        return FakeResponse(200, self.next_get)

    def post(self, url, *, json, auth, timeout, verify):
        self.post_calls.append(
            {"url": url, "json": json, "auth": auth, "timeout": timeout, "verify": verify}
        )
        return FakeResponse(200, self.next_post)


def build_driver(client=None, sleep_fn=None):
    return NetioJsonDriver(
        "netio-lab-01",
        "192.0.2.10",
        port=8080,
        config={"path": "/netio.json", "timeoutSeconds": 3, "retries": 1},
        credentials={"username": "netio", "password": "secret"},
        client=client or FakeHttpClient(),
        sleep_fn=sleep_fn,
    )


def test_netio_driver_reads_identity_and_outlets_and_uses_basic_auth():
    client = FakeHttpClient()
    driver = build_driver(client)

    assert driver.discover() == {
        "reachable": True,
        "driver": "netio-json",
        "controllerId": "netio-lab-01",
        "model": "PowerPDU 4C",
        "firmware": "3.1.0",
        "outletCount": 2,
    }
    assert driver.list_outlets() == [
        {"outlet": "1", "name": "PLC", "state": "off", "load": 12.5},
        {"outlet": "2", "name": "HMI", "state": "on", "load": 0},
    ]
    assert client.get_calls[-1] == {
        "url": "http://192.0.2.10:8080/netio.json",
        "auth": ("netio", "secret"),
        "timeout": 3,
        "verify": True,
    }


def test_netio_driver_posts_on_off_and_cycles_with_explicit_states():
    client = FakeHttpClient()
    slept = []
    driver = build_driver(client, slept.append)

    assert driver.set_outlet_state("1", "on") == {
        "outlet": "1",
        "state": "off",
        "success": True,
    }
    assert client.post_calls[-1]["json"] == {"Outputs": [{"ID": 1, "Action": 1}]}

    result = driver.cycle_outlet("2", off_seconds=7)
    assert result["outlet"] == "2"
    assert result["success"] is True
    assert slept == [7]
    assert [call["json"] for call in client.post_calls[-2:]] == [
        {"Outputs": [{"ID": 2, "Action": 0}]},
        {"Outputs": [{"ID": 2, "Action": 1}]},
    ]


def test_netio_driver_rejects_unknown_states_and_sanitizes_http_errors():
    client = FakeHttpClient()
    driver = build_driver(client)
    client.next_post = {"Outputs": [{"ID": 1, "State": 9, "Action": 6}]}

    with pytest.raises(NetioJsonError, match="unknown output state"):
        driver.set_outlet_state("1", "on")

    class UnauthorizedClient(FakeHttpClient):
        def get(self, url, *, auth, timeout, verify):
            return FakeResponse(401, {"error": "do not expose credentials"})

    with pytest.raises(NetioJsonError) as error:
        build_driver(UnauthorizedClient()).list_outlets()
    assert error.value.error_code == "AUTHENTICATION_FAILED"
    assert "credentials" not in str(error.value).lower()


def test_registry_builds_netio_driver_from_provider_credential_reference():
    registry = PowerRegistry.from_config(
        {
            "controllers": [
                {
                    "id": "netio-lab-01",
                    "name": "NETIO lab strip",
                    "driver": "netio-json",
                    "host": "192.0.2.10",
                    "port": 80,
                    "credentialRef": "netio-lab-01-http",
                    "config": {"path": "/netio.json", "useHttps": False},
                }
            ],
            "outlets": [{"controllerId": "netio-lab-01", "outlet": "1"}],
        },
        credential_resolver=lambda reference: {
            "username": "netio",
            "password": "secret",
        },
    )

    controller = registry.get("netio-lab-01")
    assert controller.driver.__class__.__name__ == "NetioJsonDriver"
    assert controller.definition.credential_ref == "netio-lab-01-http"


def test_netio_driver_rejects_invalid_outlet_id():
    driver = build_driver()

    with pytest.raises(PowerDriverError, match="positive integer"):
        driver.get_outlet_state("socket-a")
