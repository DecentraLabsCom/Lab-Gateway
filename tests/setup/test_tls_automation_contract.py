import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"
INIT_SSL = ROOT / "openresty" / "init-ssl.sh"
DEPLOY_HOOK = ROOT / "certbot" / "deploy-hook.sh"


def service_block(service_name: str, compose_text: str) -> str:
    marker = re.search(
        rf"^  {re.escape(service_name)}:\s*$", compose_text, re.MULTILINE
    )
    assert marker is not None, service_name
    start = marker.end()
    next_service = re.search(r"^  [A-Za-z0-9_-]+:\s*$", compose_text[start:], re.MULTILINE)
    end = start + next_service.start() if next_service else len(compose_text)
    return compose_text[start:end]


class TlsAutomationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = COMPOSE_FILE.read_text(encoding="utf-8")
        cls.init_ssl = INIT_SSL.read_text(encoding="utf-8")

    def test_certbot_deploy_hook_validates_and_installs_renewed_pair(self):
        self.assertTrue(DEPLOY_HOOK.is_file())
        hook = DEPLOY_HOOK.read_text(encoding="utf-8")

        for required in (
            "RENEWED_LINEAGE",
            "TLS_CERT_HOSTNAME",
            "openssl x509",
            "openssl pkey",
            "-checkhost",
            "-checkip",
            "CERTBOT_TARGET_DIR",
            "TLS_CERT_UID",
            "TLS_CERT_GID",
            "mktemp",
            "mv -f",
            'chown "$cert_uid:$cert_gid" "$source_cert" "$source_key"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, hook)

    def test_certbot_services_mount_and_run_the_deploy_hook(self):
        for service_name in ("certbot", "certbot-init", "certbot-renew"):
            block = service_block(service_name, self.compose)
            with self.subTest(service=service_name):
                self.assertIn("./certbot/deploy-hook.sh:/usr/local/bin/deploy-hook.sh:ro", block)
                self.assertIn("TLS_CERT_UID=${HOST_UID:-1000}", block)
                self.assertIn("TLS_CERT_GID=${HOST_GID:-1000}", block)
                self.assertIn("/usr/local/bin/deploy-hook.sh", block)

    def test_existing_live_lineage_is_promoted_by_certbot_init(self):
        block = service_block("certbot-init", self.compose)
        self.assertIn("RENEWED_LINEAGE=", block)
        self.assertIn("/etc/letsencrypt/live/$$primary_domain", block)

    def test_certbot_init_uses_explicit_shell_argv(self):
        block = service_block("certbot-init", self.compose)
        self.assertRegex(
            block,
            r"entrypoint:\s*\n\s*- /bin/sh\s*\n\s*- -c\s*\n",
        )
        self.assertNotIn("entrypoint: >", block)

    def test_manual_certbot_service_uses_certbot_as_entrypoint(self):
        block = service_block("certbot", self.compose)
        self.assertIn('entrypoint: ["certbot"]', block)

    def test_openresty_uses_live_lineage_when_canonical_pair_is_unusable(self):
        for required in (
            "cert_pair_is_usable",
            "CERTBOT_DOMAINS",
            "/live/",
            "install_tls_pair",
            "using Certbot certificate",
            "TLS_RELOAD_INTERVAL_SECONDS",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.init_ssl)

    def test_openresty_does_not_try_to_run_certbot_itself(self):
        self.assertNotIn("certbot renew", self.init_ssl)
        self.assertNotIn("certbot certonly", self.init_ssl)


if __name__ == "__main__":
    unittest.main()
