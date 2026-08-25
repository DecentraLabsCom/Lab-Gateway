import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = ROOT / "setup.sh"
SETUP_BAT = ROOT / "setup.bat"
CANONICAL_BACKEND_ENTRYPOINT = ROOT / "blockchain-services" / "docker" / "entrypoint.sh"
SYNC_COMPOSE_SECRETS_SH = ROOT / "scripts" / "sync-compose-secrets.sh"
ISSUE_LITE_SH = ROOT / "scripts" / "issue-lite-trust-bundle.sh"
ISSUE_LITE_PS1 = ROOT / "scripts" / "Issue-LiteTrustBundle.ps1"
VALIDATE_GATEWAY_ENV_PY = ROOT / "scripts" / "validate-gateway-env.py"
NGINX_CONF = ROOT / "openresty" / "nginx.conf"
COMPOSE_FILE = ROOT / "docker-compose.yml"
REAL_COMPOSE_PREPARE_SCRIPT = ROOT / "tests" / "integration" / "prepare-real-compose-ci.sh"


def _service_block(service_name: str, compose_text: str) -> str:
    marker_match = re.search(
        rf"^  {re.escape(service_name)}:\s*$", compose_text, re.MULTILINE
    )
    assert marker_match is not None
    start = marker_match.end()
    next_service_match = re.search(
        r"^  [A-Za-z0-9_-]+:\s*$", compose_text[start:], re.MULTILINE
    )
    next_service = start + next_service_match.start() if next_service_match else -1
    return compose_text[start:] if next_service == -1 else compose_text[start:next_service]


GATEWAY_MANAGED_BACKEND_KEYS = [
    "ADMIN_ACCESS_TOKEN",
    "ADMIN_ACCESS_TOKEN_HEADER",
    "ADMIN_ACCESS_TOKEN_COOKIE",
    "ADMIN_ACCESS_TOKEN_REQUIRED",
    "ADMIN_DASHBOARD_LOCAL_ONLY",
    "ADMIN_DASHBOARD_ALLOW_PRIVATE",
    "SECURITY_ALLOW_PRIVATE_NETWORKS",
    "ADMIN_ALLOWED_CIDRS",
    "LAB_MANAGER_TOKEN",
    "LAB_MANAGER_TOKEN_HEADER",
    "LAB_MANAGER_TOKEN_COOKIE",
    "LAB_MANAGER_ALLOWED_CIDRS",
    "OPS_INTERNAL_AUTH_TOKEN",
    "OPS_INTERNAL_AUTH_HEADER",
    "GUACAMOLE_MYSQL_USER",
    "GUACAMOLE_MYSQL_PASSWORD",
    "BLOCKCHAIN_MYSQL_USER",
    "BLOCKCHAIN_MYSQL_PASSWORD",
    "OPS_BACKEND_MYSQL_USER",
    "OPS_BACKEND_MYSQL_PASSWORD",
    "OPS_GUACAMOLE_MYSQL_USER",
    "OPS_GUACAMOLE_MYSQL_PASSWORD",
    "RESERVATION_PROJECTION_CREDENTIALS_JSON",
]


class SetupEnvContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup_sh = SETUP_SH.read_text(encoding="utf-8")
        cls.setup_bat = SETUP_BAT.read_text(encoding="utf-8")
        cls.sync_compose_secrets_sh = SYNC_COMPOSE_SECRETS_SH.read_text(encoding="utf-8")
        cls.issue_lite_sh = ISSUE_LITE_SH.read_text(encoding="utf-8")
        cls.issue_lite_ps1 = ISSUE_LITE_PS1.read_text(encoding="utf-8")
        cls.validate_gateway_env_ps1 = (ROOT / "scripts" / "Validate-GatewayEnv.ps1").read_text(encoding="utf-8")
        cls.nginx_conf = NGINX_CONF.read_text(encoding="utf-8")
        cls.compose_file = COMPOSE_FILE.read_text(encoding="utf-8")
        cls.gateway_tests_workflow = (
            ROOT / ".github" / "workflows" / "gateway-tests.yml"
        ).read_text(encoding="utf-8")
        cls.real_compose_prepare_script = REAL_COMPOSE_PREPARE_SCRIPT.read_text(
            encoding="utf-8"
        )
        cls.init_ssl = (ROOT / "openresty" / "init-ssl.sh").read_text(encoding="utf-8")

    def test_gateway_managed_backend_keys_are_removed_from_embedded_backend_env(self):
        for key in GATEWAY_MANAGED_BACKEND_KEYS:
            with self.subTest(script="setup.sh", key=key):
                self.assertIn(
                    f'remove_env_var "$BLOCKCHAIN_ENV_FILE" "{key}"',
                    self.setup_sh,
                )
            with self.subTest(script="setup.bat", key=key):
                self.assertIn(
                    f'call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "{key}"',
                    self.setup_bat,
                )

    def test_full_access_code_redeemer_map_reaches_embedded_backend(self):
        backend_service = _service_block("blockchain-services", self.compose_file)
        self.assertIn(
            "- ACCESS_CODE_REDEEMER_CREDENTIALS_JSON=${ACCESS_CODE_REDEEMER_CREDENTIALS_JSON:-}",
            backend_service,
        )
        self.assertIn(
            "- RESERVATION_PROJECTION_CREDENTIALS_JSON=${RESERVATION_PROJECTION_CREDENTIALS_JSON:-}",
            backend_service,
        )

    def test_full_gateway_credential_maps_must_be_json_and_match_gateway_identity(self):
        invalid_env = "\n".join([
            "SERVER_NAME=lab.example",
            "ISSUER=",
            "AUTH_ACCESS_CODE_REDEEMER_TOKEN=acr-secret",
            "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON=lab.example:acr-secret",
            "SESSION_OBSERVER_GATEWAY_ID=lab.example",
            "SESSION_OBSERVER_SIGNING_SECRET=observer-secret",
            "SESSION_OBSERVER_CREDENTIALS_JSON=lab.example:observer-secret",
        ]) + "\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(invalid_env, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATE_GATEWAY_ENV_PY), "--env", str(env_file)],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ACCESS_CODE_REDEEMER_CREDENTIALS_JSON must be a JSON object", result.stderr)

    def test_full_gateway_credential_maps_accept_matching_json(self):
        valid_env = "\n".join([
            "SERVER_NAME=lab.example",
            "ISSUER=",
            "AUTH_ACCESS_CODE_REDEEMER_TOKEN=acr-secret",
            'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON={"lab.example":"acr-secret"}',
            "SESSION_OBSERVER_GATEWAY_ID=lab.example",
            "SESSION_OBSERVER_SIGNING_SECRET=observer-secret",
            'SESSION_OBSERVER_CREDENTIALS_JSON={"lab.example":"observer-secret"}',
        ]) + "\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(valid_env, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATE_GATEWAY_ENV_PY), "--env", str(env_file)],
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_gateway_credential_maps_preserve_non_default_https_port(self):
        valid_env = "\n".join([
            "SERVER_NAME=lab.example",
            "HTTPS_PORT=8443",
            "ISSUER=",
            "AUTH_ACCESS_CODE_REDEEMER_TOKEN=acr-secret",
            'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON={"lab.example:8443":"acr-secret"}',
            "SESSION_OBSERVER_GATEWAY_ID=lab.example:8443",
            "SESSION_OBSERVER_SIGNING_SECRET=observer-secret",
            'SESSION_OBSERVER_CREDENTIALS_JSON={"lab.example:8443":"observer-secret"}',
        ]) + "\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(valid_env, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATE_GATEWAY_ENV_PY), "--env", str(env_file)],
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_gateway_credential_maps_reject_hostname_only_id_on_non_default_port(self):
        invalid_env = "\n".join([
            "SERVER_NAME=lab.example",
            "HTTPS_PORT=8443",
            "ISSUER=",
            "AUTH_ACCESS_CODE_REDEEMER_TOKEN=acr-secret",
            'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON={"lab.example":"acr-secret"}',
            "SESSION_OBSERVER_GATEWAY_ID=lab.example",
            "SESSION_OBSERVER_SIGNING_SECRET=observer-secret",
            'SESSION_OBSERVER_CREDENTIALS_JSON={"lab.example":"observer-secret"}',
        ]) + "\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(invalid_env, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATE_GATEWAY_ENV_PY), "--env", str(env_file)],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gateway ID", result.stderr)

    def test_setup_validates_full_gateway_credential_maps_before_syncing_secrets(self):
        self.assertIn(
            'scripts/validate-gateway-env.py --env "$ROOT_ENV_FILE"',
            self.setup_sh,
        )
        self.assertIn(
            'scripts\\Validate-GatewayEnv.ps1" -EnvPath "%ROOT_ENV_FILE%"',
            self.setup_bat,
        )
        for key in (
            "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON",
            "SESSION_OBSERVER_CREDENTIALS_JSON",
        ):
            self.assertIn(key, self.validate_gateway_env_ps1)

    def test_gateway_setup_no_longer_writes_shared_admin_keys_to_blockchain_env(self):
        forbidden_tokens = [
            "update_env_in_all",
            "update_env_blockchain_only",
            ":UpdateEnvBoth",
            ":UpdateEnvBlockchainOnly",
            "call :UpdateEnvBoth",
            "call :UpdateEnvBlockchainOnly",
        ]
        for token in forbidden_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, self.setup_sh)
                self.assertNotIn(token, self.setup_bat)

    def test_intent_payload_key_is_configured_by_full_setup(self):
        expected_shell = [
            'existing_intent_payload_encryption_key="$(get_env_default "INTENT_PAYLOAD_ENCRYPTION_KEY" "$BLOCKCHAIN_ENV_FILE")"',
            'read -r -s -p "Intent payload encryption key (leave empty to generate): " intent_payload_encryption_key',
            'intent_payload_encryption_key="$(openssl rand -base64 32 | tr -d \'\\n\')"',
            'update_env_var "$BLOCKCHAIN_ENV_FILE" "INTENT_PAYLOAD_ENCRYPTION_KEY" "$intent_payload_encryption_key"',
        ]
        expected_bat = [
            'call :ReadEnvValue "%BLOCKCHAIN_ENV_FILE%" "INTENT_PAYLOAD_ENCRYPTION_KEY" existing_intent_payload_encryption_key',
            'call :ReadSecret "Intent payload encryption key (leave empty to generate): " intent_payload_encryption_key',
            'call :GenerateObserverSecret intent_payload_encryption_key',
            'call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "INTENT_PAYLOAD_ENCRYPTION_KEY" "!intent_payload_encryption_key!"',
        ]
        for snippet in expected_shell:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_ops_secrets_key_generation_keeps_fernet_padding_and_validates_existing_values(self):
        expected_shell = [
            'tr -d \'\\n\' | tr \'+/\' \'-_\'',
            'is_valid_fernet_key',
            'Existing OPS_SECRETS_KEY is not a valid Fernet key',
        ]
        expected_bat = [
            "[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }) -as [byte[]]).Replace('+','-').Replace('/','_')",
            ":IsValidFernetKey",
            "Existing OPS_SECRETS_KEY is not a valid Fernet key",
        ]
        for snippet in expected_shell:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_secret_synchronizers_reject_invalid_fernet_keys(self):
        expected_shell = [
            "is_valid_fernet_key()",
            '[[ "${env_key}" == "OPS_SECRETS_KEY" ]]',
            "OPS_SECRETS_KEY must be a valid 32-byte URL-safe base64 Fernet key.",
        ]
        expected_powershell = [
            "if ($mapping.Value -eq 'OPS_SECRETS_KEY'",
            "^[A-Za-z0-9_-]{43}=$",
            "OPS_SECRETS_KEY must be a valid 32-byte URL-safe base64 Fernet key.",
        ]
        sync_powershell = (ROOT / "scripts" / "Sync-ComposeSecrets.ps1").read_text(
            encoding="utf-8"
        )
        for snippet in expected_shell:
            with self.subTest(script="sync-compose-secrets.sh", snippet=snippet):
                self.assertIn(snippet, self.sync_compose_secrets_sh)
        for snippet in expected_powershell:
            with self.subTest(script="Sync-ComposeSecrets.ps1", snippet=snippet):
                self.assertIn(snippet, sync_powershell)

    def test_openresty_does_not_use_an_unrendered_server_name_placeholder(self):
        lab_access = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
        self.assertNotIn("${SERVER_NAME}", lab_access)
        self.assertIn("server_name _;", lab_access)
        self.assertIn("set_by_lua_block $ops_origin", lab_access)

    def test_backend_entrypoints_persist_generated_intent_payload_key(self):
        entrypoint = CANONICAL_BACKEND_ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("INTENT_PAYLOAD_ENCRYPTION_KEY", entrypoint)
        self.assertIn(".intent-payload-encryption-key", entrypoint)
        self.assertIn("openssl rand -base64 32", entrypoint)
        self.assertIn("export INTENT_PAYLOAD_ENCRYPTION_KEY", entrypoint)
        self.assertIn("chmod 600", entrypoint)

    def test_shared_admin_keys_are_written_to_gateway_root_env(self):
        expected_shell_writes = [
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_HEADER"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_COOKIE"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_ACCESS_TOKEN_REQUIRED"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_LOCAL_ONLY"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_DASHBOARD_ALLOW_PRIVATE"',
            'update_env_var "$ROOT_ENV_FILE" "SECURITY_ALLOW_PRIVATE_NETWORKS"',
            'update_env_var "$ROOT_ENV_FILE" "ADMIN_ALLOWED_CIDRS"',
            'update_env_var "$ROOT_ENV_FILE" "LAB_MANAGER_ALLOWED_CIDRS"',
        ]
        expected_bat_writes = [
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_HEADER"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_COOKIE"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_REQUIRED"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_LOCAL_ONLY"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_ALLOW_PRIVATE"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "SECURITY_ALLOW_PRIVATE_NETWORKS"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ALLOWED_CIDRS"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_MANAGER_ALLOWED_CIDRS"',
        ]
        for snippet in expected_shell_writes:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat_writes:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_lite_remote_lab_admin_prompts_only_for_url_and_token(self):
        self.assertIn("Lite /lab-admin Remote Backend", self.setup_sh)
        self.assertIn("Lite /lab-admin Remote Backend", self.setup_bat)
        self.assertRegex(self.setup_sh, r'read -p "LAB_ADMIN_BACKEND_URL \[empty -> blocked\]: "')
        self.assertRegex(self.setup_sh, r'read -p "LAB_ADMIN_BACKEND_TOKEN \[empty -> configure later\]: "')
        self.assertRegex(self.setup_bat, r'set /p "lab_admin_backend_url=LAB_ADMIN_BACKEND_URL \[empty -\^> blocked\]: "')
        self.assertRegex(self.setup_bat, r'set /p "lab_admin_backend_token=LAB_ADMIN_BACKEND_TOKEN \[empty -\^> configure later\]: "')

        forbidden_prompt_patterns = [
            r'read -p "LAB_ADMIN_BACKEND_TOKEN_HEADER',
            r'read -p "LAB_ADMIN_BACKEND_ALLOW_INSECURE',
            r'set /p ".*LAB_ADMIN_BACKEND_TOKEN_HEADER',
            r'set /p ".*LAB_ADMIN_BACKEND_ALLOW_INSECURE',
        ]
        for pattern in forbidden_prompt_patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.setup_sh))
                self.assertIsNone(re.search(pattern, self.setup_bat))

    def test_lite_remote_lab_admin_defaults_are_written_and_reported(self):
        expected_shell = [
            'update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"',
            'update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"',
            "LAB_ADMIN_BACKEND_URL left empty (/lab-admin remains blocked in Lite mode).",
            "LAB_ADMIN_BACKEND_TOKEN left empty.",
            "LAB_ADMIN_BACKEND_ALLOW_INSECURE set to: false",
        ]
        expected_bat = [
            'call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"',
            "LAB_ADMIN_BACKEND_URL left empty",
            "LAB_ADMIN_BACKEND_TOKEN left empty.",
            "LAB_ADMIN_BACKEND_ALLOW_INSECURE set to: false",
        ]
        for snippet in expected_shell:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_setup_prepares_lab_content_bind_mount(self):
        expected_shell = [
            "mkdir -p lab-content",
            "chmod 755 lab-content",
            'chown -R "${host_uid}:${host_gid}" certs blockchain-data lab-content',
        ]
        expected_bat = [
            "if not exist lab-content mkdir lab-content",
        ]
        for snippet in expected_shell:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_setup_derives_exact_fmu_audience_from_public_gateway_origin(self):
        expected_shell = [
            'update_env_var "$ROOT_ENV_FILE" "FMU_JWT_AUDIENCE" "${gateway_public_origin}/fmu"',
            'gateway_public_origin="https://${domain}"',
        ]
        expected_bat = [
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_JWT_AUDIENCE" "!gateway_public_origin!/fmu"',
            'set "gateway_public_origin=https://!domain!"',
        ]
        for snippet in expected_shell:
            self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            self.assertIn(snippet, self.setup_bat)

    def test_setup_env_updates_escape_sed_replacement_metacharacters(self):
        self.assertIn("local escaped_value", self.setup_sh)
        self.assertIn("escaped_value=$(printf '%s' \"$value\" | sed 's/[\\\\&|]/\\\\&/g')", self.setup_sh)
        self.assertIn('sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"', self.setup_sh)

        bash_path = shutil.which("bash")
        if bash_path is None:
            self.skipTest("bash is required to execute setup.sh's shell contract")
        bash_probe = subprocess.run(
            [bash_path, "-c", "exit 0"],
            capture_output=True,
            text=True,
        )
        if bash_probe.returncode != 0:
            self.skipTest("bash is not executable in this environment")

        function_match = re.search(r"(?ms)^update_env_var\(\) \{.*?^\}", self.setup_sh)
        if function_match is None:
            raise AssertionError("update_env_var function should be present")

        value = r"a|b&c\d"
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("TOKEN=old\n", encoding="utf-8")
            script = (
                f"{function_match.group(0)}\n"
                'update_env_var "$1" "TOKEN" "$2"\n'
            )
            subprocess.run(
                [bash_path, "-c", script, "bash", env_file.as_posix(), value],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(env_file.read_text(encoding="utf-8"), f"TOKEN={value}\n")

    def test_lite_bundle_binds_technical_gateway_id_to_public_origin_host_and_port(self):
        self.assertIn("lite_public_origin", self.issue_lite_sh)
        self.assertIn("read -r lite_public_origin full_origin server_name gateway_id", self.issue_lite_sh)
        self.assertIn('echo "SERVER_NAME=${server_name}"', self.issue_lite_sh)
        self.assertIn('safe_gateway_id="${gateway_id//:/_}"', self.issue_lite_sh)
        self.assertIn('gateway_id = host + (f":{port}" if port and port != 443 else "")', self.issue_lite_sh)
        self.assertNotIn("<gateway-id>", self.issue_lite_sh)

        self.assertIn("LitePublicOrigin", self.issue_lite_ps1)
        self.assertIn('"SERVER_NAME=$($lite.HostName)"', self.issue_lite_ps1)
        self.assertIn('$GatewayId = $lite.GatewayId', self.issue_lite_ps1)
        self.assertIn("$GatewayId.Replace(':', '_')", self.issue_lite_ps1)
        self.assertNotIn("[string]$GatewayId", self.issue_lite_ps1)

    def test_lite_bundle_and_setup_wire_session_ticket_endpoints_to_full(self):
        for script in (self.issue_lite_sh, self.issue_lite_ps1):
            self.assertIn("AUTH_SESSION_TICKET_ISSUE_URL", script)
            self.assertIn("AUTH_SESSION_TICKET_REDEEM_URL", script)

        for script in (self.setup_sh, self.setup_bat):
            self.assertIn("bundle_server_name", script)
            self.assertIn("bundle_ticket_issue_url", script)
            self.assertIn("bundle_ticket_redeem_url", script)
            self.assertIn("AUTH_SESSION_TICKET_ISSUE_URL", script)
            self.assertIn("AUTH_SESSION_TICKET_REDEEM_URL", script)

    def test_lite_bundle_registers_a_dedicated_guacamole_provisioner_route(self):
        for script in (self.issue_lite_sh, self.issue_lite_ps1):
            self.assertIn("GUACAMOLE_PROVISIONER_ROUTES_JSON", script)
            self.assertIn("GUACAMOLE_PROVISIONER_TOKEN", script)
            self.assertIn("X-Guacamole-Provisioner-Token", script)

        for script in (self.setup_sh, self.setup_bat):
            self.assertIn("bundle_guacamole_provisioner_token", script)
            self.assertIn("GUACAMOLE_PROVISIONER_TOKEN", script)
            self.assertIn("GUACAMOLE_PROVISIONER_TOKEN_HEADER", script)

        self.assertIn("env GUACAMOLE_PROVISIONER_TOKEN;", self.nginx_conf)
        self.assertIn("env GUACAMOLE_PROVISIONER_TOKEN_HEADER;", self.nginx_conf)
        self.assertIn("GUACAMOLE_PROVISIONER_TOKEN_FILE=/run/secrets/guacamole_provisioner_token", self.compose_file)
        self.assertGreaterEqual(self.compose_file.count("guacamole_provisioner_token"), 2)

    def test_ops_worker_has_a_separate_gateway_internal_credential(self):
        for script in (self.setup_sh, self.setup_bat):
            self.assertIn("OPS_INTERNAL_AUTH_TOKEN", script)
            self.assertIn("X-Ops-Internal-Token", script)

        self.assertIn("env OPS_INTERNAL_AUTH_TOKEN;", self.nginx_conf)
        self.assertIn("env OPS_INTERNAL_AUTH_HEADER;", self.nginx_conf)
        self.assertIn("OPS_INTERNAL_AUTH_TOKEN_FILE=/run/secrets/ops_internal_auth_token", self.compose_file)
        self.assertGreaterEqual(self.compose_file.count("ops_internal_auth_token"), 2)

    def test_database_principals_are_separated_in_compose(self):
        mysql_script = (ROOT / "mysql" / "000-ensure-user.sh").read_text(encoding="utf-8")
        for key in (
            "GUACAMOLE_MYSQL_USER",
            "BLOCKCHAIN_MYSQL_USER",
            "OPS_BACKEND_MYSQL_USER",
            "OPS_GUACAMOLE_MYSQL_USER",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.compose_file)
        self.assertIn("GRANT ALL PRIVILEGES ON \\`${escaped_mysql_database}\\`.* TO '${escaped_guacamole_mysql_user}'", mysql_script)
        self.assertIn("GRANT ALL PRIVILEGES ON \\`${escaped_blockchain_db}\\`.* TO '${escaped_blockchain_mysql_user}'", mysql_script)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON", mysql_script)
        self.assertIn("grant_guacamole_worker_tables", mysql_script)
        self.assertIsNone(re.search(r"GRANT ALL PRIVILEGES ON .*escaped_ops_", mysql_script))
        for key in ("GUACAMOLE_MYSQL_PASSWORD", "OPS_BACKEND_MYSQL_PASSWORD", "OPS_GUACAMOLE_MYSQL_PASSWORD"):
            self.assertIn(f"{key}_FILE=", self.compose_file)
        self.assertIsNone(re.search(r"^\s*- MYSQL_PASSWORD=|^\s*MYSQL_PASSWORD:", self.compose_file, re.MULTILINE))

    def test_local_compose_secrets_are_files_for_read_only_services(self):
        secret_mappings = {
            "mysql_root_password": "MYSQL_ROOT_PASSWORD",
            "guacamole_mysql_password": "GUACAMOLE_MYSQL_PASSWORD",
            "blockchain_mysql_password": "BLOCKCHAIN_MYSQL_PASSWORD",
            "ops_backend_mysql_password": "OPS_BACKEND_MYSQL_PASSWORD",
            "ops_guacamole_mysql_password": "OPS_GUACAMOLE_MYSQL_PASSWORD",
            "guac_admin_pass": "GUAC_ADMIN_PASS",
            "admin_access_token": "ADMIN_ACCESS_TOKEN",
            "lab_manager_token": "LAB_MANAGER_TOKEN",
            "ops_internal_auth_token": "OPS_INTERNAL_AUTH_TOKEN",
            "ops_secrets_key": "OPS_SECRETS_KEY",
            "auth_access_code_redeemer_token": "AUTH_ACCESS_CODE_REDEEMER_TOKEN",
            "session_observation_ingest_token": "SESSION_OBSERVATION_INGEST_TOKEN",
            "guacamole_provisioner_token": "GUACAMOLE_PROVISIONER_TOKEN",
            "aas_service_token": "AAS_SERVICE_TOKEN",
            "lab_admin_backend_token": "LAB_ADMIN_BACKEND_TOKEN",
            "fmu_station_internal_token": "FMU_STATION_INTERNAL_TOKEN",
            "auth_session_ticket_internal_token": "AUTH_SESSION_TICKET_INTERNAL_TOKEN",
            "session_observer_signing_secret": "SESSION_OBSERVER_SIGNING_SECRET",
            "fmu_proxy_signing_key": "FMU_PROXY_SIGNING_KEY",
        }
        for secret_name, env_key in secret_mappings.items():
            with self.subTest(secret=secret_name):
                self.assertIn(f"file: ./secrets/{secret_name}", self.compose_file)
                self.assertIn(f"write_compose_secret {secret_name} {env_key}", self.setup_sh)
                self.assertIn(f'call :WriteComposeSecret "{secret_name}" "{env_key}"', self.setup_bat)

        self.assertNotIn("environment: ADMIN_ACCESS_TOKEN", self.compose_file)
        self.assertNotIn("environment: MYSQL_ROOT_PASSWORD", self.compose_file)

    def test_compose_secret_files_are_readable_by_non_root_container_users(self):
        # File-backed Compose secrets preserve the source-file mode inside the
        # container. The directory remains restricted, while each mounted file
        # must be readable by image-specific non-root service users whose UID
        # may differ from HOST_UID.
        self.assertIn('chmod 644 "$temporary_path"', self.setup_sh)
        self.assertIn('chown "${owner_uid}:${owner_gid}" "$temporary_path"', self.setup_sh)
        self.assertIn('mktemp "${secret_path}.tmp.XXXXXX"', self.setup_sh)
        self.assertIn('chmod 644 "${temporary_path}"', self.sync_compose_secrets_sh)
        self.assertIn('chmod 750 "${SECRETS_DIR}"', self.sync_compose_secrets_sh)

    def test_mysql_entrypoint_removes_conflicting_root_password_file_variable(self):
        entrypoint = (ROOT / "mysql" / "ensure-user-entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("load_secret MYSQL_ROOT_PASSWORD /run/secrets/mysql_root_password", entrypoint)
        self.assertIn("unset MYSQL_ROOT_PASSWORD_FILE", entrypoint)

    def test_mysql_reconciler_runs_after_official_initialization(self):
        entrypoint = (ROOT / "mysql" / "ensure-user-entrypoint.sh").read_text(encoding="utf-8")

        self.assertIn('ENSURE_SCRIPT="/usr/local/bin/ensure-user.sh"', entrypoint)
        self.assertIn("mysql --protocol=tcp -h 127.0.0.1", entrypoint)
        self.assertIn("set -Eeo pipefail", entrypoint)
        self.assertNotIn("set -Eeuo pipefail", entrypoint)
        self.assertIn(
            "./mysql/000-ensure-user.sh:/usr/local/bin/ensure-user.sh:ro",
            self.compose_file,
        )
        self.assertNotIn(
            "./mysql/000-ensure-user.sh:/docker-entrypoint-initdb.d/000-ensure-user.sh:ro",
            self.compose_file,
        )

    def test_lite_does_not_start_embedded_backend_or_cross_fallback_jwt_keys(self):
        self.assertIn("BLOCKCHAIN_SERVICES_ENABLED", self.compose_file)
        self.assertIn("- ISSUER=${ISSUER:-}", self.compose_file)
        self.assertIn("Embedded blockchain-services disabled (Lite mode)", self.compose_file)
        init_lua = (ROOT / "openresty" / "lua" / "init.lua").read_text()
        self.assertIn('active_key_path = "/etc/ssl/private/public_key.pem"', init_lua)
        self.assertIn('active_key_path = "/etc/openresty/jwt-keys/public_key.pem"', init_lua)
        self.assertIn('config:set("jwt_public_key_path", active_key_path)', init_lua)
        self.assertIn('FULL_JWT_PUBLIC_KEY="/etc/openresty/jwt-keys/public_key.pem"', self.init_ssl)
        self.assertIn('JWT_PUBLIC_KEY="$FULL_JWT_PUBLIC_KEY"', self.init_ssl)

    def test_embedded_backend_receives_access_code_encryption_key(self):
        self.assertIn(
            "- ACCESS_CODE_ENCRYPTION_KEY=${ACCESS_CODE_ENCRYPTION_KEY:-}",
            self.compose_file,
        )
        self.assertIn(
            "- FMU_ACCESS_STATE_PATH=${FMU_ACCESS_STATE_PATH:-/var/lib/openresty/fmu-access}",
            self.compose_file,
        )
        self.assertIn(
            "./fmu-access-state:${FMU_ACCESS_STATE_PATH:-/var/lib/openresty/fmu-access}",
            self.compose_file,
        )
        self.assertIn("env ACCESS_CODE_ENCRYPTION_KEY;", self.nginx_conf)

    def test_optional_fmu_profile_and_openresty_runtime_defaults_are_explicit(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("FMU_RUNNER_ENABLED=false", env_example)
        self.assertIn("FMU_LOCAL_REALTIME_ENABLED=false", env_example)
        self.assertIn('FMU_RUNNER_ENABLED=${FMU_RUNNER_ENABLED:-false}', self.compose_file)
        self.assertIn('AUTO_LOGOUT_ON_DISCONNECT=${AUTO_LOGOUT_ON_DISCONNECT:-true}', self.compose_file)
        self.assertIn('ADMIN_TRUST_FORWARDED_IP=${ADMIN_TRUST_FORWARDED_IP:-true}', self.compose_file)
        init_lua = (ROOT / "openresty" / "lua" / "init.lua").read_text(encoding="utf-8")
        self.assertIn("fmu_runner_enabled = false", init_lua)

    def test_setup_maps_selected_fmu_mode_to_the_matching_compose_profile(self):
        expected_shell = [
            'fmu_runner_profile="fmu-local-dev"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_BACKEND_MODE" "local"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_DEV_MODE" "true"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_REALTIME_ENABLED" "true"',
            'fmu_runner_profile="fmu-runner"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_BACKEND_MODE" "station"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_DEV_MODE" "false"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_REALTIME_ENABLED" "false"',
            'compose_profiles="--profile $fmu_runner_profile"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_DEV_MODE" "false"',
            'update_env_var "$ROOT_ENV_FILE" "FMU_LOCAL_REALTIME_ENABLED" "false"',
        ]
        expected_bat = [
            'set "fmu_runner_profile=fmu-local-dev"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_BACKEND_MODE" "local"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "true"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_REALTIME_ENABLED" "true"',
            'set "fmu_runner_profile=fmu-runner"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_BACKEND_MODE" "station"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "false"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_REALTIME_ENABLED" "false"',
            'set "compose_full=!compose_full! --profile !fmu_runner_profile!"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "false"',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_REALTIME_ENABLED" "false"',
        ]
        for snippet in expected_shell:
            with self.subTest(script="setup.sh", snippet=snippet):
                self.assertIn(snippet, self.setup_sh)
        for snippet in expected_bat:
            with self.subTest(script="setup.bat", snippet=snippet):
                self.assertIn(snippet, self.setup_bat)

    def test_selected_services_restart_after_host_or_docker_restart(self):
        for service in ("guacamole", "fmu-runner-local"):
            with self.subTest(service=service):
                service_block = _service_block(service, self.compose_file)
                self.assertRegex(service_block, r"(?m)^\s+restart:\s+(?:always|unless-stopped)\s*$")

        for script in (self.setup_sh, self.setup_bat):
            with self.subTest(script="setup", script_text=script):
                self.assertIn("fmu-local-dev", script)
                self.assertIn("fmu-runner", script)

    def test_lua_random_source_is_available_with_openssl_in_runtime_and_test_runners(self):
        files = (
            ROOT / "openresty" / "Dockerfile",
            ROOT / "openresty" / "tests" / "run-lua-tests.sh",
            ROOT / "openresty" / "tests" / "run-lua-tests.ps1",
            ROOT / ".github" / "workflows" / "gateway-tests.yml",
            ROOT / ".github" / "workflows" / "release.yml",
        )

        for path in files:
            with self.subTest(path=path):
                self.assertIn("lua-resty-openssl", path.read_text(encoding="utf-8"))

        random_module = (ROOT / "openresty" / "lua" / "resty" / "random.lua").read_text(encoding="utf-8")
        self.assertIn('ffi.load("crypto")', random_module)

    def test_openresty_does_not_install_unused_lua_resty_string_dependency(self):
        dockerfile = (ROOT / "openresty" / "Dockerfile").read_text(encoding="utf-8")

        self.assertNotIn("lua-resty-string", dockerfile)

    def test_web_tests_checkout_initializes_embedded_backend_submodule(self):
        web_tests = self.gateway_tests_workflow.split("\n  web-tests:", 1)[1].split(
            "\n  test-summary:", 1
        )[0]

        self.assertIn("submodules: recursive", web_tests)

    def test_real_compose_ci_prepares_writable_state_for_the_runner_identity(self):
        script = self.real_compose_prepare_script

        self.assertIn('host_uid="$(id -u)"', script)
        self.assertIn('host_gid="$(id -g)"', script)
        self.assertIn('set_env HOST_UID "$host_uid" "$ROOT_ENV_FILE"', script)
        self.assertIn('set_env HOST_GID "$host_gid" "$ROOT_ENV_FILE"', script)
        self.assertIn('mkdir -p "$ROOT_DIR/blockchain-data/keys"', script)
        self.assertIn('"$ROOT_DIR/ops-data"', script)

if __name__ == "__main__":
    unittest.main()
