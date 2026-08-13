import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from power.drivers.netio_json import NetioJsonDriver


class NetioSmokeHandler(BaseHTTPRequestHandler):
    state = {1: 0, 2: 1}

    def log_message(self, *_args):
        return

    def _payload(self):
        return {
            "Agent": {"Model": "Smoke NETIO", "Version": "test"},
            "Outputs": [
                {"ID": 1, "Name": "PLC", "State": self.state[1], "Action": 6, "Load": 1.2},
                {"ID": 2, "Name": "HMI", "State": self.state[2], "Action": 6, "Load": 0},
            ],
        }

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/netio.json":
            self._send({"error": "not found"}, 404)
            return
        self._send(self._payload())

    def do_POST(self):
        if self.path != "/netio.json":
            self._send({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        command = json.loads(self.rfile.read(length).decode("utf-8"))
        for output in command.get("Outputs", []):
            output_id = int(output["ID"])
            action = int(output.get("Action", 6))
            if action in {0, 1}:
                self.state[output_id] = action
        self._send(self._payload())


def test_netio_driver_smoke_uses_real_local_http_json_round_trip():
    NetioSmokeHandler.state = {1: 0, 2: 1}
    server = ThreadingHTTPServer(("127.0.0.1", 0), NetioSmokeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        driver = NetioJsonDriver(
            "netio-smoke",
            "127.0.0.1",
            port=server.server_address[1],
            config={"path": "/netio.json", "timeoutSeconds": 2, "retries": 1},
            sleep_fn=lambda _seconds: None,
        )

        assert driver.discover()["reachable"] is True
        assert driver.set_outlet_state("1", "on")["state"] == "on"
        assert driver.get_outlet_state("1")["state"] == "on"
        assert driver.cycle_outlet("1", off_seconds=1)["state"] == "on"
        assert driver.list_outlets()[0]["load"] == 1.2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
