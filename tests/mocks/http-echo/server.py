from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os


class EchoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._respond()

    def do_HEAD(self):
        self._respond(include_body=False)

    def do_POST(self):
        self._respond()

    def do_PUT(self):
        self._respond()

    def do_PATCH(self):
        self._respond()

    def do_DELETE(self):
        self._respond()

    def do_OPTIONS(self):
        self._respond(include_body=False)

    def _respond(self, *, include_body=True):
        body = os.environ.get("ECHO_BODY", "ok").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), EchoHandler).serve_forever()
