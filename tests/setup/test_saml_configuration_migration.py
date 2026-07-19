import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "scripts" / "migrate-saml-env.py"


def test_migration_merges_template_issuer_without_overwriting_existing_values():
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temp_dir:
        temp_path = Path(temp_dir)
        env_path = temp_path / ".env"
        template_path = temp_path / ".env.example"
        env_path.write_text(
            'SAML_IDP_METADATA_OVERRIDE={"https://custom.example/idp":"https://custom.example/metadata"}\n',
            encoding="utf-8",
        )
        template_path.write_text(
            'SAML_IDP_METADATA_OVERRIDE={"https://sir2.example/idp":"https://sir2.example/metadata"}\n'
            "SAML_IDP_METADATA_TLS_PROFILE={}\n"
            "SAML_METADATA_HEALTH_CACHE_MS=30000\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(MIGRATION), "--env", str(env_path), "--template", str(template_path)],
            check=True,
            capture_output=True,
            text=True,
        )

        values = dict(
            line.split("=", 1)
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        overrides = json.loads(values["SAML_IDP_METADATA_OVERRIDE"])
        assert overrides == {
            "https://sir2.example/idp": "https://sir2.example/metadata",
            "https://custom.example/idp": "https://custom.example/metadata",
        }
        assert values["SAML_IDP_METADATA_TLS_PROFILE"] == "{}"
        assert values["SAML_METADATA_HEALTH_CACHE_MS"] == "30000"
        assert "applied" in result.stdout


def test_setup_scripts_invoke_saml_migration():
    setup_sh = (ROOT / "setup.sh").read_text(encoding="utf-8")
    setup_bat = (ROOT / "setup.bat").read_text(encoding="utf-8")

    assert "migrate-saml-env.py" in setup_sh
    assert ":MigrateSamlEnv" in setup_bat
    assert "Migrate-SamlEnv.ps1" in setup_bat
