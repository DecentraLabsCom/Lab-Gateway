#!/usr/bin/env python3
"""
Mock FMU Runner for integration testing.

Simulates the FMU Runner endpoints:
  GET  /health                          → {"status": "UP"}
  GET  /api/v1/simulations/describe     → model metadata
  POST /api/v1/simulations/run          → simulation results (or error)

Supports:
  - Concurrency tracking per labId  (returns 429 when MAX_CONCURRENT reached)
  - Simulated timeout                (POST with ?simulateTimeout=true → 504)
  - Auth header validation           (checks Authorization header from OpenResty)
"""

import json
import os
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlparse, parse_qs

PORT = int(os.getenv("PORT", "8090"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_PER_MODEL", "2"))
SIMULATE_TIMEOUT_DELAY = float(os.getenv("SIMULATE_TIMEOUT_DELAY", "0"))  # 0 = no delay

# Concurrency tracking
_active: dict = defaultdict(int)
_lock = Lock()

# Tracks all received requests for assertion endpoints
_request_log: list = []


MOCK_DESCRIBE = {
    "fmiVersion": "2.0",
    "simulationType": "CoSimulation",
    "defaultStartTime": 0.0,
    "defaultStopTime": 10.0,
    "defaultStepSize": 0.01,
    "modelVariables": [
        {"name": "mass", "causality": "input", "type": "Real", "unit": "kg", "start": 1.0, "min": 0.1, "max": 100},
        {"name": "damping", "causality": "input", "type": "Real", "unit": "N.s/m", "start": 0.5},
        {"name": "position", "causality": "output", "type": "Real", "unit": "m"},
        {"name": "velocity", "causality": "output", "type": "Real", "unit": "m/s"},
    ],
}

MOCK_RUN_RESULT = {
    "status": "completed",
    "simulationTime": 0.42,
    "time": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    "outputs": {
        "position": [0.0, 0.15, 0.35, 0.5, 0.58, 0.6],
        "velocity": [0.0, 0.98, 1.1, 0.9, 0.5, 0.2],
    },
    "outputVariables": ["position", "velocity"],
}


def json_response(handler, status, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if headers:
        for k, v in headers.items():
            handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silent

    def _require_bearer(self):
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            json_response(self, 401, {"detail": "Missing or invalid Bearer token"})
            return False
        return True

    def _log_request(self, method):
        _request_log.append({
            "method": method,
            "path": self.path,
            "headers": dict(self.headers),
            "timestamp": time.time(),
        })

    def do_GET(self):
        self._log_request("GET")
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Health
        if parsed.path == "/health":
            json_response(self, 200, {"status": "UP"})
            return

        # Describe
        if parsed.path == "/api/v1/simulations/describe":
            if not self._require_bearer():
                return
            fmu_name = params.get("fmuFileName", [None])[0]
            if not fmu_name:
                json_response(self, 422, {"detail": "Missing fmuFileName query parameter"})
                return
            json_response(self, 200, MOCK_DESCRIBE)
            return

        # Test helper: return request log
        if parsed.path == "/_test/request-log":
            json_response(self, 200, {"requests": _request_log})
            return

        # Test helper: reset state
        if parsed.path == "/_test/reset":
            _request_log.clear()
            with _lock:
                _active.clear()
            json_response(self, 200, {"reset": True})
            return

        json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        self._log_request("POST")
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/v1/simulations/run":
            if not self._require_bearer():
                return
            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(content_length)
            try:
                body = json.loads(body_raw) if body_raw else {}
            except json.JSONDecodeError:
                json_response(self, 400, {"detail": "Invalid JSON body"})
                return

            # Check Authorization header (set by OpenResty from JTI cookie)
            auth_header = self.headers.get("Authorization", "")

            lab_id = body.get("labId", "unknown")

            # Simulate timeout if requested
            if "simulateTimeout" in params:
                delay = float(params.get("simulateTimeout", ["5"])[0])
                time.sleep(delay)
                json_response(self, 504, {"detail": "Simulation timed out"})
                return

            # Concurrency check
            with _lock:
                if _active[lab_id] >= MAX_CONCURRENT:
                    json_response(self, 429, {
                        "detail": f"Concurrency limit ({MAX_CONCURRENT}) reached for this FMU."
                    })
                    return
                _active[lab_id] += 1

            try:
                # Simulate processing time (configurable for concurrency tests).
                delay = SIMULATE_TIMEOUT_DELAY if SIMULATE_TIMEOUT_DELAY > 0 else 0.05
                time.sleep(delay)

                result = dict(MOCK_RUN_RESULT)
                result["labId"] = lab_id
                result["receivedAuth"] = auth_header
                json_response(self, 200, result)
            finally:
                with _lock:
                    _active[lab_id] = max(0, _active[lab_id] - 1)
            return

        json_response(self, 404, {"error": "not found"})


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Mock FMU Runner listening on port {PORT}")
    print(f"Max concurrent per model: {MAX_CONCURRENT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
