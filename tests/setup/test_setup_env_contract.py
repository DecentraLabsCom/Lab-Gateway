import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = ROOT / "setup.sh"
SETUP_BAT = ROOT / "setup.bat"


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
]


class SetupEnvContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup_sh = SETUP_SH.read_text(encoding="utf-8")
        cls.setup_bat = SETUP_BAT.read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
