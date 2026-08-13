import json
import os
import socket
import socketserver
import sys
from threading import Thread

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.apc_snmp import APC_LEGACY_OIDS, ApcPowerNetSnmpDriver


class ApcSmokeUdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        payload = json.loads(self.request[0].decode("utf-8"))
        server = self.server
        operation = payload.get("operation")
        oid = str(payload.get("oid") or "")

        if operation == "get":
            response = {"value": server.value_for(oid)}
        elif operation == "set":
            response = {"value": server.set_value(oid, int(payload["value"]))}
        elif operation == "walk":
            response = {"rows": server.walk_values(oid)}
        else:
            response = {"error": "unsupported operation"}

        self.request[1].sendto(json.dumps(response).encode("utf-8"), self.client_address)


class ApcSmokeUdpServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True

    def __init__(self, address):
        super().__init__(address, ApcSmokeUdpHandler)
        self.state = {1: 2, 2: 1}

    def value_for(self, oid):
        if oid == APC_LEGACY_OIDS["model"]:
            return "AP7920B-SMOKE"
        if oid == APC_LEGACY_OIDS["firmware"]:
            return "v3.9.4-smoke"
        if oid == APC_LEGACY_OIDS["outlet_count"]:
            return 2
        for outlet, state in self.state.items():
            if oid == f"{APC_LEGACY_OIDS['state']}.{outlet}":
                return state
            if oid == f"{APC_LEGACY_OIDS['name']}.{outlet}":
                return {1: "PLC", 2: "HMI"}[outlet]
        raise KeyError(oid)

    def set_value(self, oid, value):
        for outlet in self.state:
            if oid != f"{APC_LEGACY_OIDS['command']}.{outlet}":
                continue
            if value == 1:
                self.state[outlet] = 1
            elif value == 2:
                self.state[outlet] = 2
            elif value == 3:
                self.state[outlet] = 1
            else:
                raise ValueError(value)
            return value
        raise KeyError(oid)

    def walk_values(self, oid):
        del oid
        return []


class UdpSnmpSmokeClient:
    """Small stateful UDP test double for the driver's SnmpClient contract."""

    def __init__(self, host, port):
        self.address = (host, port)

    def _request(self, operation, oid, value=None):
        payload = {"operation": operation, "oid": oid}
        if value is not None:
            payload["value"] = value
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.sendto(json.dumps(payload).encode("utf-8"), self.address)
            response, _ = client.recvfrom(4096)
        body = json.loads(response.decode("utf-8"))
        if "error" in body:
            raise RuntimeError(body["error"])
        return body

    def get(self, oid):
        return self._request("get", oid)["value"]

    def set(self, oid, value):
        return self._request("set", oid, value)["value"]

    def walk(self, oid):
        return self._request("walk", oid)["rows"]


def test_apc_driver_smoke_uses_stateful_local_snmp_round_trip():
    server = ApcSmokeUdpServer(("127.0.0.1", 0))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        driver = ApcPowerNetSnmpDriver(
            "apc-smoke",
            "127.0.0.1",
            port=server.server_address[1],
            config={"profile": "legacy", "timeoutSeconds": 2, "retries": 1},
            credentials={"version": "v2c", "community": "smoke"},
            client=UdpSnmpSmokeClient("127.0.0.1", server.server_address[1]),
        )

        assert driver.discover() == {
            "reachable": True,
            "driver": "apc-powernet-snmp",
            "controllerId": "apc-smoke",
            "profile": "legacy",
            "model": "AP7920B-SMOKE",
            "firmware": "v3.9.4-smoke",
            "outletCount": 2,
        }
        assert driver.list_outlets() == [
            {"outlet": "1", "name": "PLC", "state": "off"},
            {"outlet": "2", "name": "HMI", "state": "on"},
        ]
        assert driver.set_outlet_state("1", "on")["success"] is True
        assert driver.get_outlet_state("1") == {"outlet": "1", "state": "on"}
        assert driver.cycle_outlet("1", off_seconds=1)["state"] == "on"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
