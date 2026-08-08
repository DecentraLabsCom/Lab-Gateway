"""Opt-in release gate for the real local integration stack.

The runner is intentionally configuration-driven because the Marketplace,
provider backends and Station are deployed with environment-specific URLs and
credentials. It does not fabricate those values. When configured, it performs
real HTTP, Redis REST, JSON-RPC and Docker-restart operations.

Minimum infrastructure variables:

    RELEASE_GATE_ENABLED=1
    REDIS_REST_URL=http://127.0.0.1:16379
    REDIS_REST_TOKEN=release-gate-token
    ANVIL_RPC_URL=http://127.0.0.1:18545
    COMPOSE_FILE=tests/e2e/docker-compose.release-gate.yml
    COMPOSE_PROJECT_NAME=<temporary project>

Application endpoints are enabled by setting RELEASE_GATE_APPLICATIONS to a
JSON object, for example:

    {"marketplace":"https://marketplace.test",
     "consumer":"http://127.0.0.1:18081",
     "provider":"http://127.0.0.1:18082",
     "gateway":"https://127.0.0.1:18443"}

Additional authenticated or destructive scenarios can be expressed in
RELEASE_GATE_SCENARIO_FILE. The runner requires an expected status for every
request, and can restart a service between two requests.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def _env_json(name: str, default: Any) -> Any:
    raw = os.environ.get(name)
    return default if not raw else json.loads(raw)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for key, replacement in os.environ.items():
            result = result.replace("${" + key + "}", replacement)
        return result
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _request(
    url: str,
    method: str = "GET",
    body: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15,
) -> HttpResponse:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if payload is not None else {}),
            **(headers or {}),
        },
    )
    context = ssl._create_unverified_context() if url.lower().startswith("https://") else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return HttpResponse(response.status, response.read(), dict(response.headers.items()))
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, error.read(), dict(error.headers.items()))


def _wait_for_http(url: str, timeout: float = 120) -> HttpResponse:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = _request(url, timeout=5)
            if response.status < 500:
                return response
            last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as error:  # pragma: no cover - depends on external stack
            last_error = error
        time.sleep(2)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


class ReleaseGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("RELEASE_GATE_ENABLED") != "1":
            raise unittest.SkipTest(
                "Set RELEASE_GATE_ENABLED=1; this suite intentionally never runs against implicit defaults"
            )
        cls.compose_file = os.environ.get("COMPOSE_FILE", "")
        cls.compose_project = os.environ.get("COMPOSE_PROJECT_NAME", "")
        cls.compose_services = os.environ.get("RELEASE_GATE_SERVICES", "redis,mysql,anvil").split(",")

    def _compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["docker", "compose"]
        if self.compose_project:
            command.extend(["-p", self.compose_project])
        if self.compose_file:
            command.extend(["-f", self.compose_file])
        command.extend(args)
        return subprocess.run(command, check=check, capture_output=True, text=True)

    def _restart(self, service: str) -> None:
        result = self._compose("restart", service, check=False)
        self.assertEqual(
            result.returncode,
            0,
            f"Could not restart {service}:\n{result.stdout}\n{result.stderr}",
        )

    def _service_container(self, service: str) -> str:
        result = self._compose("ps", "-q", service, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        container = result.stdout.strip().splitlines()
        self.assertTrue(container, f"Compose service {service} is not running")
        return container[0]

    def _assert_service_healthy(self, service: str) -> None:
        container = self._service_container(service)
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}", container],
            check=True,
            capture_output=True,
            text=True,
        )
        status = result.stdout.strip()
        self.assertEqual(status, "healthy", f"{service} is not healthy: {status}")

    def _wait_for_service_healthy(self, service: str, timeout: float = 120) -> None:
        deadline = time.monotonic() + timeout
        last_status = "missing"
        while time.monotonic() < deadline:
            container = self._service_container(service)
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}",
                    container,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            last_status = result.stdout.strip()
            if last_status == "healthy":
                return
            time.sleep(2)
        self.fail(f"Timed out waiting for {service} to become healthy: {last_status}")

    def test_real_compose_dependencies_are_healthy(self) -> None:
        """The gate starts with real MySQL, Redis and Anvil, never mocks."""

        for service in self.compose_services:
            with self.subTest(service=service):
                self._assert_service_healthy(service)

    def test_redis_atomic_commands_and_durability_survive_restart(self) -> None:
        rest_url = os.environ.get("REDIS_REST_URL")
        token = os.environ.get("REDIS_REST_TOKEN")
        self.assertTrue(rest_url, "REDIS_REST_URL is required")
        self.assertTrue(token, "REDIS_REST_TOKEN is required")
        headers = {"Authorization": f"Bearer {token}"}
        key = f"release-gate:{os.getpid()}:{time.time_ns()}"

        def command(*parts: str) -> Any:
            response = _request(rest_url, "POST", list(parts), headers)
            self.assertEqual(response.status, 200, response.body.decode("utf-8", errors="replace"))
            return response.json()["result"]

        try:
            self.assertEqual(command("SET", key, "prepared", "EX", "300"), "OK")
            self.assertIsNone(command("SET", key, "second-writer", "NX"))
            script = "return redis.call('SET', KEYS[1], ARGV[1], 'XX')"
            self.assertEqual(command("EVAL", script, "1", key, "committed"), "OK")
            self.assertEqual(command("GET", key), "committed")

            self._restart(os.environ.get("REDIS_RESTART_SERVICE", "redis"))
            _wait_for_http(f"{rest_url.rstrip('/')}/health")
            self.assertEqual(command("GET", key), "committed")
        finally:
            _request(rest_url, "POST", ["DEL", key], headers)

    def test_mysql_durable_marker_survives_restart(self) -> None:
        if os.environ.get("MYSQL_TEST_ENABLED", "1") != "1":
            return

        service = os.environ.get("MYSQL_RESTART_SERVICE", "mysql")
        user = os.environ.get("MYSQL_TEST_USER", "release_gate")
        password = os.environ.get("MYSQL_TEST_PASSWORD", "release-gate-password")
        database = os.environ.get("MYSQL_TEST_DATABASE", "blockchain_services")
        marker = f"{os.getpid()}_{time.time_ns()}"

        def sql(statement: str) -> str:
            result = self._compose(
                "exec",
                "-T",
                service,
                "mysql",
                f"-u{user}",
                f"-p{password}",
                f"-D{database}",
                "-Nse",
                statement,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"MySQL command failed: {result.stderr}")
            return result.stdout.strip()

        table = "release_gate_durable_marker"
        try:
            sql(
                f"CREATE TABLE IF NOT EXISTS {table} "
                "(marker VARCHAR(128) PRIMARY KEY, value VARCHAR(128) NOT NULL) ENGINE=InnoDB"
            )
            sql(f"REPLACE INTO {table} (marker, value) VALUES ('{marker}', 'committed')")
            self._restart(service)
            self._wait_for_service_healthy(service)
            self.assertEqual(sql(f"SELECT value FROM {table} WHERE marker = '{marker}'"), "committed")
        finally:
            try:
                self._wait_for_service_healthy(service)
                sql(f"DELETE FROM {table} WHERE marker = '{marker}'")
            except (AssertionError, subprocess.CalledProcessError):
                # Compose cleanup removes the isolated volume after a failed
                # run; do not hide the assertion that caused the failure.
                pass

    def test_anvil_rpc_and_deployed_contract_evidence(self) -> None:
        rpc_url = os.environ.get("ANVIL_RPC_URL")
        self.assertTrue(rpc_url, "ANVIL_RPC_URL is required")

        request_id = 0

        def rpc(method: str, params: list[Any]) -> Any:
            nonlocal request_id
            request_id += 1
            response = _request(
                rpc_url,
                "POST",
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            )
            self.assertEqual(response.status, 200, response.body.decode("utf-8", errors="replace"))
            result = response.json()
            self.assertNotIn("error", result, result)
            return result["result"]

        chain_id = int(rpc("eth_chainId", []), 16)
        expected_chain_id = int(os.environ.get("EXPECTED_CHAIN_ID", str(chain_id)))
        self.assertEqual(chain_id, expected_chain_id)

        before = int(rpc("eth_blockNumber", []), 16)
        rpc("evm_mine", [])
        after = int(rpc("eth_blockNumber", []), 16)
        self.assertGreaterEqual(after, before + 1)

        contract_address = os.environ.get("CONTRACT_ADDRESS")
        if not contract_address:
            return
        code = rpc("eth_getCode", [contract_address, "latest"])
        self.assertNotEqual(code, "0x", "configured Diamond address has no deployed bytecode")
        expected_code = os.environ.get("EXPECTED_CONTRACT_CODE")
        if expected_code:
            self.assertEqual(code.lower(), expected_code.lower())
        expected_code_hash = os.environ.get("EXPECTED_CONTRACT_CODE_HASH")
        if expected_code_hash:
            # hashlib.sha3_256 is deliberately not used: its padding differs
            # from Ethereum Keccak-256. Use Foundry's cast when this optional
            # assertion is enabled.
            cast = subprocess.run(
                ["cast", "keccak", code], check=True, capture_output=True, text=True
            ).stdout.strip()
            self.assertEqual(cast.lower(), expected_code_hash.lower())

    def test_configured_application_surfaces_are_live_without_intercepts(self) -> None:
        applications = _env_json("RELEASE_GATE_APPLICATIONS", {})
        require_applications = os.environ.get("RELEASE_GATE_REQUIRE_APPLICATIONS") == "1"
        if require_applications:
            self.assertTrue(applications, "RELEASE_GATE_APPLICATIONS is required for a production gate")

        paths = {
            "marketplace": "/api/market/labs?limit=1",
            "consumer": "/actuator/health/readiness",
            "provider": "/actuator/health/readiness",
            "gateway": "/health",
            "guacamole": "/health",
            "station": "/health",
        }
        for name, base_url in applications.items():
            with self.subTest(application=name):
                path = paths.get(name, "/health")
                response = _wait_for_http(f"{base_url.rstrip('/')}{path}")
                self.assertEqual(response.status, 200, response.body[:1000])
                if name == "marketplace":
                    body = response.json()
                    self.assertIsInstance(body.get("labs"), list)
                    self.assertIn("catalogueStatus", body)

    def test_configured_scenarios_have_explicit_outcomes(self) -> None:
        scenario_file = os.environ.get("RELEASE_GATE_SCENARIO_FILE")
        if not scenario_file:
            return
        scenarios = _expand_env(json.loads(Path(scenario_file).read_text(encoding="utf-8")))
        self.assertIsInstance(scenarios, list)
        self.assertTrue(scenarios)

        for scenario in scenarios:
            with self.subTest(scenario=scenario.get("name")):
                self.assertIn("name", scenario)
                self.assertIn("url", scenario)
                self.assertIn("expectedStatus", scenario)
                if scenario.get("restartBefore"):
                    self._restart(scenario["restartBefore"])
                response = _request(
                    scenario["url"],
                    scenario.get("method", "GET"),
                    scenario.get("body"),
                    scenario.get("headers"),
                )
                expected = scenario["expectedStatus"]
                expected_statuses = expected if isinstance(expected, list) else [expected]
                self.assertIn(response.status, expected_statuses, response.body[:1000])
                if "bodyContains" in scenario:
                    body = response.body.decode("utf-8", errors="replace")
                    self.assertIn(scenario["bodyContains"], body)
                if scenario.get("restartAfter"):
                    self._restart(scenario["restartAfter"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
