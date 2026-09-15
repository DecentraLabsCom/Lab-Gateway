import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "tests" / "integration" / "verify-compose-profiles.ps1"
INIT_SSL = ROOT / "openresty" / "init-ssl.sh"
INIT_LUA = ROOT / "openresty" / "lua" / "init.lua"
NGINX_CONF = ROOT / "openresty" / "nginx.conf"
ACCESS_CONF = ROOT / "openresty" / "gateway.conf"

class ComposeProfileSmokeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
        cls.init_ssl = INIT_SSL.read_text(encoding="utf-8")
        cls.init_lua = INIT_LUA.read_text(encoding="utf-8")
        cls.nginx = NGINX_CONF.read_text(encoding="utf-8")
        cls.access = ACCESS_CONF.read_text(encoding="utf-8")

    def test_profile_smoke_is_reproducible_and_does_not_open_tunnels(self):
        self.assertTrue(SMOKE_SCRIPT.is_file())
        for profile in (
            "fmu-runner",
            "fmu-local-dev",
            "aas",
            "certbot",
            "cloudflare",
            "cloudflare-token",
        ):
            with self.subTest(profile=profile):
                self.assertIn(f'"{profile}"', self.smoke)
                self.assertIn(f"--profile $profile", self.smoke)
        self.assertIn("config -q", self.smoke)
        self.assertIn('"cloudflared", "--version"', self.smoke)
        self.assertIn("certbot-init", self.smoke)
        self.assertIn("finally", self.smoke)
        self.assertNotIn("tunnel --url", self.smoke)
        self.assertNotIn("cloudflared tunnel", self.smoke)

    def test_openresty_has_a_writable_jwt_rotation_fallback(self):
        for required in (
            'REMOTE_JWT_PUBLIC_KEY="$SSL_DIR/public_key.pem"',
            'JWT_ROTATION_STATE_DIR=',
            'JWT_REMOTE_PUBLIC_KEY_PATH',
            'JWT_PREVIOUS_PUBLIC_KEY_PATH',
            "JWT_STATE_WRITE_TEST",
            "using writable JWT rotation state",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.init_ssl)

        self.assertIn("JWT_REMOTE_PUBLIC_KEY_PATH", self.nginx)
        self.assertIn("JWT_PREVIOUS_PUBLIC_KEY_PATH", self.nginx)
        self.assertIn("JWT_REMOTE_PUBLIC_KEY_PATH", self.init_lua)
        self.assertIn("jwt_public_key_path", self.access)


if __name__ == "__main__":
    unittest.main()
