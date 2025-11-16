import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


ACTIVE_CONNECTIONS = {
    "conn-1": {"username": "SmokeUser"}
}


def json_response(handler, status, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence default logging to keep smoke output clean
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/guacamole/":
            body = b"<html><body>mock guacamole</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.startswith("/guacamole/api/session/data/"):
            json_response(self, 200, ACTIVE_CONNECTIONS)
            return

        if parsed.path == "/guacamole/api/echo":
            auth = self.headers.get("Authorization")
            json_response(self, 200, {"authorization": auth})
            return

        json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/guacamole/api/tokens":
            json_response(self, 200, {
                "authToken": "admin-token",
                "dataSource": "smoke",
                "username": "SmokeUser"
            })
            return
        json_response(self, 404, {"error": "not found"})

    def do_PATCH(self):
        if self.path.startswith("/guacamole/api/session/data/"):
            json_response(self, 204, {})
            return
        json_response(self, 404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/guacamole/api/tokens/"):
            self.send_response(204)
            self.end_headers()
            return
        json_response(self, 404, {"error": "not found"})


def main():
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
