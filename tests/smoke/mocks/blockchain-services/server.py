#!/usr/bin/env python3
"""Minimal auth backend used by the OpenResty smoke stack."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock


ACCESS_CODE = "smoke-access-code"
MARKETPLACE_AUTHORIZATION = "Bearer smoke-marketplace-token"
JWT_PATH = "/data/jwt.txt"
redeemed = False
redeem_lock = Lock()


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    if handler.headers.get("Transfer-Encoding", "").lower() == "chunked":
        chunks: list[bytes] = []
        while True:
            size_line = handler.rfile.readline().strip()
            if not size_line:
                continue
            size = int(size_line.split(b";", 1)[0], 16)
            if size == 0:
                handler.rfile.readline()
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.read(2)
        raw = b"".join(chunks)
    else:
        length = int(handler.headers.get("Content-Length", "0"))
        raw = handler.rfile.read(length) if length else b"{}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/auth/access-code/issue":
            if self.headers.get("X-Marketplace-Authorization") != MARKETPLACE_AUTHORIZATION:
                write_json(self, 403, {"error": "Marketplace authentication required"})
                return
            request = read_json(self)
            if not isinstance(request.get("token"), str):
                write_json(self, 400, {"error": "token is required"})
                return
            write_json(self, 200, {"accessCode": ACCESS_CODE, "labURL": "https://lab.test:18443/guacamole/"})
            return

        if self.path == "/auth/access-code/redeem":
            request = read_json(self)
            global redeemed
            with redeem_lock:
                if request.get("accessCode") != ACCESS_CODE or redeemed:
                    write_json(self, 401, {"error": "Invalid or expired access code"})
                    return
                redeemed = True
            with open(JWT_PATH, "r", encoding="utf-8") as jwt_file:
                token = jwt_file.read().strip()
            write_json(self, 200, {"token": token, "labURL": "https://lab.test:18443/guacamole/"})
            return

        write_json(self, 404, {"error": "not found"})

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), AuthHandler).serve_forever()
