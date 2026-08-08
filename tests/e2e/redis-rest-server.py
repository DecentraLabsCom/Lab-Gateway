"""Small Redis REST bridge used by the real Marketplace E2E stack.

Marketplace talks to Redis through the Upstash-compatible REST protocol while
the local integration stack uses a real Redis server. Keeping this adapter in
the test stack lets the E2E run exercise the same atomic commands (including
Lua EVAL) without replacing Redis with an in-memory fake.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def normalize_redis_value(value: Any) -> Any:
    """Convert redis-py byte values to JSON-safe values recursively."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, tuple):
        return [normalize_redis_value(item) for item in value]
    if isinstance(value, list):
        return [normalize_redis_value(item) for item in value]
    if isinstance(value, dict):
        return {
            normalize_redis_value(key): normalize_redis_value(item)
            for key, item in value.items()
        }
    return value


def _redis_client():
    # Import lazily so unit tests for the protocol helpers do not need a Redis
    # client installed on the host.
    import redis

    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=10,
    )


class RedisRestHandler(BaseHTTPRequestHandler):
    server_version = "DecentraLabsRedisREST/1.0"

    def _authorized(self) -> bool:
        if os.environ.get("REDIS_REST_ALLOW_ANONYMOUS", "false").lower() == "true":
            return True
        expected = os.environ.get("REDIS_REST_TOKEN", "")
        return bool(expected) and self.headers.get("Authorization") == f"Bearer {expected}"

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/health":
            self._write_json(404, {"error": "not found"})
            return
        try:
            _redis_client().ping()
        except Exception as exc:  # pragma: no cover - exercised by compose
            self._write_json(503, {"error": f"redis unavailable: {exc}"})
            return
        self._write_json(200, {"status": "UP"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._authorized():
            self._write_json(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            command = json.loads(self.rfile.read(length))
            if not isinstance(command, list) or not command or not all(
                isinstance(part, (str, int, float)) for part in command
            ):
                raise ValueError("request body must be a non-empty Redis command array")
            result = _redis_client().execute_command(*command)
            self._write_json(200, {"result": normalize_redis_value(result)})
        except ValueError as exc:
            self._write_json(400, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - exercised by compose
            self._write_json(500, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep compose logs useful without duplicating every successful probe.
        if self.command != "GET" or self.path != "/health":
            super().log_message(format, *args)


def main() -> None:
    host = os.environ.get("REDIS_REST_HOST", "0.0.0.0")
    port = int(os.environ.get("REDIS_REST_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), RedisRestHandler)
    print(f"Redis REST bridge listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
