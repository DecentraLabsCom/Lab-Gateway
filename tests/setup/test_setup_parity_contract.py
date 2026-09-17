from dataclasses import dataclass
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = ROOT / "setup.sh"
SETUP_BAT = ROOT / "setup.bat"


@dataclass(frozen=True)
class SetupScriptInventory:
    env_keys: frozenset[str]
    compose_secrets: frozenset[tuple[str, str]]
    lifecycle_positions: tuple[int, ...]


LIFECYCLE_MARKERS = {
    "prerequisites": {
        "sh": r"command -v docker",
        "bat": r"^docker --version",
    },
    "submodule": {
        "sh": r"^git submodule update --init --recursive blockchain-services",
        "bat": r"^git submodule update --init --recursive blockchain-services",
    },
    "existing_env": {
        "sh": r"^existing_mysql_root_password=.*get_env_default",
        "bat": r'^call :ReadEnvValue "%ROOT_ENV_FILE%" "MYSQL_ROOT_PASSWORD"',
    },
    "saml_migration": {
        "sh": r"^\s*migrate_saml_env\s*$",
        "bat": r"^\s*call :MigrateSamlEnv\s*$",
    },
    "issuer_mode": {
        "sh": r'^echo "JWT Issuer',
        "bat": r"^echo JWT Issuer",
    },
    "fmu_runner": {
        "sh": r'^echo "FMU Runner Integration',
        "bat": r"^echo FMU Runner Integration",
    },
    "aas": {
        "sh": r'^echo "AAS Support',
        "bat": r"^echo AAS Support",
    },
    "cloudflare": {
        "sh": r'^echo "Remote Access',
        "bat": r"^echo Remote Access",
    },
    "state_secrets": {
        "sh": r"^# Docker Compose local secrets",
        "bat": r"^call :SyncComposeSecrets",
    },
    "certbot": {
        "sh": r'^echo "Certbot',
        "bat": r"^echo Certbot",
    },
    "start_prompt": {
        "sh": r"^# Ask if user wants to start services",
        "bat": r'^set /p "start_services=',
    },
}


REQUIRED_ENV_KEYS = {
    "MYSQL_ROOT_PASSWORD",
    "GUACAMOLE_MYSQL_PASSWORD",
    "BLOCKCHAIN_MYSQL_PASSWORD",
    "OPS_BACKEND_MYSQL_PASSWORD",
    "OPS_GUACAMOLE_MYSQL_PASSWORD",
    "OPS_SECRETS_KEY",
    "ADMIN_ACCESS_TOKEN",
    "LAB_MANAGER_TOKEN",
    "OPS_INTERNAL_AUTH_TOKEN",
    "AUTH_ACCESS_CODE_REDEEMER_TOKEN",
    "SESSION_OBSERVATION_INGEST_TOKEN",
    "GUACAMOLE_PROVISIONER_TOKEN",
    "RESERVATION_PROJECTION_TOKEN",
    "FMU_RUNNER_ENABLED",
    "FMU_BACKEND_MODE",
    "FMU_LOCAL_DEV_MODE",
    "FMU_LOCAL_REALTIME_ENABLED",
    "BASYX_AAS_URL",
    "AAS_ALLOWED_HOSTS",
    "AAS_SERVICE_TOKEN",
    "CLOUDFLARE_TUNNEL_TOKEN",
    "CERTBOT_DOMAINS",
    "CERTBOT_EMAIL",
    "SERVER_NAME",
    "HTTPS_PORT",
    "HTTP_PORT",
    "FMU_JWT_AUDIENCE",
}


def _first_position(text: str, pattern: str) -> int:
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    assert match is not None, f"Missing setup contract marker: {pattern}"
    return match.start()


def _env_keys(text: str, windows: bool) -> frozenset[str]:
    if windows:
        pattern = r'(?im)^\s*call\s+:UpdateEnv(?:FromVariable)?\s+"[^"]+"\s+"([A-Z][A-Z0-9_]*)"'
    else:
        pattern = r'(?m)^\s*update_env_var\s+"[^"\n]+"\s+"([A-Z][A-Z0-9_]*)"'
    return frozenset(re.findall(pattern, text))


def _compose_secrets(text: str, windows: bool) -> frozenset[tuple[str, str]]:
    if windows:
        pattern = (
            r'(?im)^\s*call\s+:WriteComposeSecret\s+'
            r'"([A-Za-z0-9_-]+)"\s+"([A-Z][A-Z0-9_]*)"'
        )
    else:
        pattern = (
            r'(?m)^\s*write_compose_secret\s+'
            r'([A-Za-z0-9_-]+)\s+([A-Z][A-Z0-9_]*)\s+"\$host_uid"\s+"\$host_gid"'
        )
    return frozenset(re.findall(pattern, text))


def _inventory(path: Path, windows: bool) -> SetupScriptInventory:
    text = path.read_text(encoding="utf-8")
    platform = "bat" if windows else "sh"
    positions = tuple(
        _first_position(text, markers[platform])
        for markers in LIFECYCLE_MARKERS.values()
    )
    return SetupScriptInventory(
        env_keys=_env_keys(text, windows),
        compose_secrets=_compose_secrets(text, windows),
        lifecycle_positions=positions,
    )


def test_setup_scripts_keep_the_same_ordered_lifecycle():
    shell = _inventory(SETUP_SH, windows=False)
    windows = _inventory(SETUP_BAT, windows=True)

    assert all(
        earlier < later
        for earlier, later in zip(shell.lifecycle_positions, shell.lifecycle_positions[1:])
    )
    assert all(
        earlier < later
        for earlier, later in zip(windows.lifecycle_positions, windows.lifecycle_positions[1:])
    )


def test_setup_scripts_keep_the_environment_key_contract():
    shell = _inventory(SETUP_SH, windows=False)
    windows = _inventory(SETUP_BAT, windows=True)

    assert REQUIRED_ENV_KEYS <= shell.env_keys
    assert REQUIRED_ENV_KEYS <= windows.env_keys
    # Linux additionally persists the UID/GID used for bind-mounted secrets;
    # Windows applies ACLs instead and intentionally has no equivalent update.
    assert shell.env_keys - windows.env_keys == {
        "HOST_UID",
        "HOST_GID",
        "COMPOSE_FILE",
        "WOL_LAN_PARENT",
        "WOL_LAN_SUBNET",
        "WOL_LAN_IP_RANGE",
    }
    assert windows.env_keys - shell.env_keys == set()


def test_setup_scripts_materialize_the_same_compose_secret_inventory():
    shell = _inventory(SETUP_SH, windows=False)
    windows = _inventory(SETUP_BAT, windows=True)

    assert shell.compose_secrets == windows.compose_secrets
    assert len(shell.compose_secrets) == 20


def test_setup_scripts_preserve_feature_and_side_effect_boundaries():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    markers = {
        "full_lite_modes": (
            ("Full mode", "Lite mode"),
            ("Full mode", "Lite mode"),
        ),
        "fmu_backends": (("FMU_BACKEND_MODE", "local"), ("FMU_BACKEND_MODE", "local")),
        "aas_settings": (("BASYX_AAS_URL", "AAS_ALLOWED_HOSTS", "AAS_SERVICE_TOKEN"),) * 2,
        "cloudflare_token": (("CLOUDFLARE_TUNNEL_TOKEN",),) * 2,
        "certbot_settings": (("CERTBOT_DOMAINS", "CERTBOT_EMAIL"),) * 2,
        "env_validation": (("validate-gateway-env.py",), ("Validate-GatewayEnv.ps1",)),
        "permissions": (("secure_gateway_state", "chmod"), (":SecureEnvFile", ":SecureSecretTree")),
        "compose_build": (("$compose_full build --no-cache",), ("call !compose_full! build --no-cache",)),
        "compose_up": (("$compose_full $compose_up_args",), ("call !compose_full! !compose_up_args!",)),
    }
    for name, (shell_needles, windows_needles) in markers.items():
        with_marker = (
            (shell_text, shell_needles),
            (windows_text, windows_needles),
        )
        for text, needles in with_marker:
            for needle in needles:
                assert needle.lower() in text.lower(), f"Missing {name} marker: {needle}"


PROMPT_CONTRACT = {
    "overwrite": (
        'read -p "Do you want to overwrite it? (y/N): "',
        'set /p "overwrite=Do you want to overwrite it? (y/N): "',
    ),
    "intent_encryption": (
        'read -r -s -p "Intent payload encryption key (leave empty to generate): "',
        'call :ReadSecret "Intent payload encryption key (leave empty to generate): "',
    ),
    "mysql_root": (
        'read -p "MySQL root password: "',
        'set /p "mysql_root_password=MySQL root password: "',
    ),
    "guacamole_credentials": (
        'read -p "Guacamole admin username [guacadmin]: "',
        'set /p "guac_admin_user=Guacamole admin username [guacadmin]: "',
    ),
    "guacamole_password": (
        'read -p "Guacamole admin password (leave empty for auto-generated): "',
        'set /p "guac_admin_pass=Guacamole admin password (leave empty for auto-generated): "',
    ),
    "admin_token": (
        'read -p "Admin access token (leave empty for auto-generated): "',
        'set /p "access_token=Admin access token (leave empty for auto-generated): "',
    ),
    "dashboard_scope": (
        'read -p "Choose [1/2] (default: 1): "',
        'set /p "dashboard_access_scope=Choose [1/2] (default: 1): "',
    ),
    "private_cidrs": (
        'read -p "Allowed private CIDRs (comma-separated, leave empty for any private range): "',
        'set /p "admin_allowed_cidrs=Allowed private CIDRs (comma-separated, leave empty for any private range): "',
    ),
    "lab_manager_token": (
        'read -p "Lab Manager token (leave empty for auto-generated): "',
        'set /p "lab_manager_token=Lab Manager token (leave empty for auto-generated): "',
    ),
    "lab_manager_cidrs": (
        'read -p "LAB_MANAGER_ALLOWED_CIDRS [empty]: "',
        'set /p "lab_manager_allowed_cidrs=LAB_MANAGER_ALLOWED_CIDRS [empty]: "',
    ),
    "winrm_cidrs": (
        'read -p "WINRM_MANAGEMENT_CIDRS [',
        'set /p "winrm_management_cidrs=WINRM_MANAGEMENT_CIDRS [',
    ),
    "demo_enable": (
        'read -p "Enable anonymous demo binding now? [y/N]: "',
        'set /p "demo_enabled=Enable anonymous demo binding now? [y/N]: "',
    ),
    "demo_lab": (
        'read -p "Demo lab ID (uint256): "',
        'set /p "demo_lab_id=Demo lab ID (uint256): "',
    ),
    "demo_connection": (
        'read -p "Demo Guacamole connection_id (positive integer): "',
        'set /p "demo_connection_id=Demo Guacamole connection_id (positive integer): "',
    ),
    "marketplace_authority": (
        'read -p "Marketplace authority URL [',
        'set /p "demo_marketplace_input=Marketplace authority URL [',
    ),
    "domain": (
        'read -p "Domain: "',
        'set /p "domain=Domain: "',
    ),
    "deployment_mode": (
        'read -p "Choose [1/2] (default: 1): " deploy_mode',
        'set /p "deploy_mode=Choose [1/2] (default: 1): "',
    ),
    "public_https": (
        'read -p "Public HTTPS port (the port clients use;',
        'set /p "public_https=Public HTTPS port (the port clients use,',
    ),
    "local_https": (
        'read -p "Local HTTPS port to bind on this host (router forwards here; default: 443): "',
        'set /p "local_https=Local HTTPS port to bind on this host (default: 443): "',
    ),
    "public_http": (
        'read -p "Public HTTP port (default: 80): "',
        'set /p "public_http=Public HTTP port (default: 80): "',
    ),
    "local_http": (
        'read -p "Local HTTP port to bind on this host (default: 80): "',
        'set /p "local_http=Local HTTP port to bind on this host (default: 80): "',
    ),
    "direct_https": (
        'read -p "HTTPS port (default: 443): " direct_https',
        'set /p "direct_https=HTTPS port (default: 443): "',
    ),
    "direct_http": (
        'read -p "HTTP port (default: 80): " direct_http',
        'set /p "direct_http=HTTP port (default: 80): "',
    ),
    "issuer": (
        'read -p "ISSUER [empty->Full, https://full/auth->Lite]: "',
        'set /p "issuer_value=ISSUER [empty->Full, https://full/auth->Lite]: "',
    ),
    "lite_backend_url": (
        'read -p "LAB_ADMIN_BACKEND_URL [empty -> blocked]: "',
        'set /p "lab_admin_backend_url=LAB_ADMIN_BACKEND_URL [empty -^> blocked]: "',
    ),
    "lite_backend_token": (
        'read -p "LAB_ADMIN_BACKEND_TOKEN [empty -> configure later]: "',
        'set /p "lab_admin_backend_token=LAB_ADMIN_BACKEND_TOKEN [empty -^> configure later]: "',
    ),
    "trust_bundle": (
        'read -p "Trust bundle path: "',
        'set /p "lite_trust_bundle=Trust bundle path: "',
    ),
    "fmu_enable": (
        'read -p "Enable FMU runner integration? [$fmu_prompt]: "',
        'set /p "enable_fmu_runner=Enable FMU runner integration? [!fmu_prompt!]: "',
    ),
    "fmu_backend": (
        'read -p "FMU execution backend [station/local] (default: ${current_fmu_backend_mode}): "',
        'set /p "selected_fmu_backend_mode=FMU execution backend [station/local] (default: !current_fmu_backend_mode!): "',
    ),
    "aas_option": (
        'read -p "AAS server [1/2/3] (default: 1): "',
        'set /p "aas_option=AAS server [1/2/3] (default: 1): "',
    ),
    "external_aas_url": (
        'read -p "External AAS API base URL (HTTPS only, e.g. https://my-aas.example.com): "',
        'set /p "external_aas_url=External AAS API base URL ^(HTTPS only, e.g. https://my-aas.example.com^): "',
    ),
    "aas_allowed_hosts": (
        'read -p "Exact allowlisted AAS hostname (without port, e.g. my-aas.example.com): "',
        'set /p "aas_allowed_hosts=Exact allowlisted AAS hostname ^(without port^): "',
    ),
    "aas_token": (
        'read -s -p "Dedicated AAS service token (leave empty to generate): "',
        'set /p "aas_service_token=Dedicated AAS service token ^(leave empty to generate^): "',
    ),
    "cloudflare_enable": (
        'read -p "Enable Cloudflare Tunnel to expose the gateway without opening inbound ports? (y/N): "',
        'set /p "enable_cf=Enable Cloudflare Tunnel to expose the gateway without opening inbound ports? (y/N): "',
    ),
    "cloudflare_token": (
        'read -p "Cloudflare Tunnel token (leave empty to use a Quick Tunnel): "',
        'set /p "cf_token=Cloudflare Tunnel token (leave empty to use a Quick Tunnel): "',
    ),
    "certbot_domains": (
        'read -p "Domains for TLS (comma-separated, leave empty to skip ACME): "',
        'set /p "cb_domains=Domains for TLS (comma-separated, leave empty to skip ACME): "',
    ),
    "certbot_email": (
        'read -p "Email for ACME (leave empty to skip ACME): "',
        'set /p "cb_email=Email for ACME (leave empty to skip ACME): "',
    ),
    "sepolia_rpc": (
        'read -p "Comma-separated Sepolia RPC URLs [',
        'set /p "sepolia_rpc=Sepolia RPC URLs (comma separated) [',
    ),
    "allowed_origins": (
        'read -p "Allowed origins for CORS [',
        'set /p "allowed_origins=Allowed origins for CORS [',
    ),
    "marketplace_key": (
        'read -p "Marketplace public key URL [',
        'set /p "marketplace_pk=Marketplace public key URL [',
    ),
    "start_services": (
        'read -p "Do you want to start the services now? (Y/n): "',
        'set /p "start_services=Do you want to start the services now? (Y/n): "',
    ),
}


def test_setup_scripts_keep_the_prompt_and_default_contract():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    assert len(PROMPT_CONTRACT) == 41
    for prompt_name, (shell_marker, windows_marker) in PROMPT_CONTRACT.items():
        assert shell_marker in shell_text, f"Missing shell prompt contract: {prompt_name}"
        assert windows_marker in windows_text, f"Missing Windows prompt contract: {prompt_name}"

    # Empty answers keep the documented safe defaults and do not silently
    # activate optional integrations.
    branch_contract = {
        "local_domain": (
            ('if [ -z "$domain" ]; then', 'domain="localhost"'),
            ('if not defined domain set "domain=localhost"',),
        ),
        "local_dashboard": (
            ('if [ "$dashboard_access_scope" = "2" ]; then', 'ADMIN_DASHBOARD_LOCAL_ONLY" "true"'),
            ('if "!dashboard_access_scope!"=="2"', 'ADMIN_DASHBOARD_LOCAL_ONLY" "true"'),
        ),
        "disabled_fmu": (
            ('fmu_runner_enabled="false"', 'FMU_LOCAL_DEV_MODE" "false"'),
            ('FMU_RUNNER_ENABLED" "false"', 'FMU_LOCAL_DEV_MODE" "false"'),
        ),
        "bundled_aas_default": (
            ('case "$aas_option" in', 'aas_bundled=true'),
            ('else (', 'set "aas_enabled=1"'),
        ),
        "quick_tunnel": (
            ('CLOUDFLARE_TUNNEL_TOKEN" ""', 'cf_enabled=true'),
            ('CLOUDFLARE_TUNNEL_TOKEN" ""', 'set "cf_enabled=1"'),
        ),
        "skip_certbot": (
            ('if [ -n "$cb_domains" ] && [ -n "$cb_email" ]; then', 'Skipped certbot configuration'),
            ('if not "%cb_domains%"=="" if not "%cb_email%"==""', 'Skipped certbot configuration'),
        ),
        "disabled_fmu_scale": (
            ('compose_up_args="up -d --scale fmu-runner=0"',),
            ('set "compose_up_args=up -d --scale fmu-runner=0"',),
        ),
    }
    for branch_name, (shell_markers, windows_markers) in branch_contract.items():
        for text, markers in (
            (shell_text, shell_markers),
            (windows_text, windows_markers),
        ):
            for marker in markers:
                assert marker in text, f"Missing {branch_name} default marker: {marker}"


FAILURE_CONTRACT = {
    "insecure_guacamole_password": (
        'Refusing to use insecure Guacamole admin password. Set a strong value.',
        'Refusing to use insecure Guacamole admin password. Set a strong value.',
    ),
    "invalid_demo_binding": (
        'Demo lab ID or connection_id is invalid; refusing to enable the demo.',
        'Demo lab ID or connection_id is invalid; refusing to enable the demo.',
    ),
    "missing_lite_bundle": (
        'A Full-issued trust bundle is required in Lite mode.',
        'A Full-issued trust bundle is required in Lite mode.',
    ),
    "invalid_fmu_backend": (
        'Invalid FMU execution backend:',
        'Invalid FMU execution backend:',
    ),
    "trust_issuer_mismatch": (
        'Trust bundle ISSUER does not match the configured Full issuer.',
        'Trust bundle ISSUER does not match the configured Full issuer.',
    ),
    "environment_validation": (
        'scripts/validate-gateway-env.py --env "$ROOT_ENV_FILE"',
        'Validate-GatewayEnv.ps1" -EnvPath "%ROOT_ENV_FILE%"',
    ),
    "compose_failure": (
        'Failed to start services. Check the error messages above.',
        'Failed to start services. Check the error messages above.',
    ),
}


def test_setup_scripts_preserve_failure_contracts():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    for failure_name, (shell_marker, windows_marker) in FAILURE_CONTRACT.items():
        assert shell_marker in shell_text, f"Missing shell failure contract: {failure_name}"
        assert windows_marker in windows_text, f"Missing Windows failure contract: {failure_name}"

    assert 'exit 1' in shell_text
    assert 'exit /b 1' in windows_text
    assert 'exit 0' in shell_text
    assert 'goto skip_start' in windows_text


def test_linux_setup_configures_the_gatewayless_station_lan_overlay():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    for marker in (
        "configure_station_lan_overlay()",
        'read -p "Enable direct physical Station LAN WoL overlay? (y/N): "',
        'update_env_var "$ROOT_ENV_FILE" "COMPOSE_FILE"',
        'update_env_var "$ROOT_ENV_FILE" "WOL_LAN_PARENT"',
        'update_env_var "$ROOT_ENV_FILE" "WOL_LAN_SUBNET"',
        'update_env_var "$ROOT_ENV_FILE" "WOL_LAN_IP_RANGE"',
        'remove_env_var "$ROOT_ENV_FILE" "WOL_LAN_GATEWAY"',
    ):
        assert marker in shell_text, f"Missing Linux Station LAN setup marker: {marker}"

    assert "The macvlan Station LAN overlay is Linux-only; setup.bat leaves it disabled." in windows_text
    assert ":DisableLinuxStationLanOverlay" in windows_text


def test_setup_documentation_describes_the_station_lan_prompt_boundary():
    english = (ROOT / "docs" / "install" / "install-setup-script.md").read_text(encoding="utf-8")
    spanish = (ROOT / "docs" / "install" / "instalar-setup-script.md").read_text(encoding="utf-8")

    assert "Station LAN" in english
    assert "Linux-only" in english
    assert "LAN física" in spanish
    assert "overlay exclusivo" in spanish
    assert "de Linux" in spanish


def _assert_order(text: str, name: str, markers: tuple[str, ...]) -> None:
    positions = []
    for marker in markers:
        position = text.find(marker)
        assert position >= 0, f"Missing {name} state marker: {marker}"
        positions.append(position)
    assert positions == sorted(positions), f"Unexpected {name} order: {markers}"


def _assert_positions(name: str, positions: tuple[int, ...]) -> None:
    assert all(position >= 0 for position in positions), f"Missing {name} state marker"
    assert positions == tuple(sorted(positions)), f"Unexpected {name} order: {positions}"


def test_setup_scripts_preserve_state_materialization_and_start_gates():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    _assert_positions(
        "shell environment migration",
        (
            shell_text.rfind('cp .env.example "$ROOT_ENV_FILE"'),
            shell_text.find("\nmigrate_saml_env\n"),
            shell_text.find("\nremove_gateway_managed_backend_env\n"),
        ),
    )
    _assert_positions(
        "Windows environment migration",
        (
            windows_text.rfind('copy ".env.example" "%ROOT_ENV_FILE%"'),
            windows_text.find("call :MigrateSamlEnv"),
            windows_text.find("call :RemoveGatewayManagedBackendEnv"),
        ),
    )
    _assert_order(
        shell_text,
        "shell state validation",
        ('secure_gateway_state\n', 'scripts/validate-gateway-env.py --env "$ROOT_ENV_FILE"', '\nsync_compose_secrets\n'),
    )
    _assert_order(
        windows_text,
        "Windows state validation",
        ('call :SecureEnvFile "%ROOT_ENV_FILE%"', 'Validate-GatewayEnv.ps1" -EnvPath "%ROOT_ENV_FILE%"', 'call :SyncComposeSecrets'),
    )
    _assert_order(
        shell_text,
        "shell start gate",
        (
            'read -p "Do you want to start the services now? (Y/n): "',
            '$compose_full down --remove-orphans',
            '$compose_full build --no-cache',
            '\nif $compose_full $compose_up_args; then',
        ),
    )
    _assert_order(
        windows_text,
        "Windows start gate",
        (
            'set /p "start_services=Do you want to start the services now? (Y/n): "',
            'call !compose_full! down --remove-orphans',
            'call !compose_full! build --no-cache',
            '\ncall !compose_full! !compose_up_args!\n',
        ),
    )

    for text in (shell_text, windows_text):
        for state_path in (
            "certs",
            "blockchain-data",
            "fmu-access-state",
            "lab-content",
            "fmu-data",
            "fmu-proxy-runtime",
            "ops-data",
            "secrets",
        ):
            assert state_path in text


TOPOLOGY_CONTRACT = {
    "full_gateway": {
        "shell": (
            'if [ -z "$issuer_value" ]; then',
            'update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_SERVICES_ENABLED" "true"',
            'update_env_var "$BLOCKCHAIN_ENV_FILE" "BLOCKCHAIN_SERVICES_MODE" "provider-consumer"',
        ),
        "windows": (
            'if "!issuer_value!"=="" (',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_SERVICES_ENABLED" "true"',
            'call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "BLOCKCHAIN_SERVICES_MODE" "provider-consumer"',
        ),
        "compose": (
            "blockchain-services:",
            'BLOCKCHAIN_SERVICES_ENABLED=${BLOCKCHAIN_SERVICES_ENABLED:-auto}',
            'if [ "$$mode" = "false" ]',
        ),
    },
    "lite_gateway": {
        "shell": (
            'if [ -n "$issuer_value" ]; then',
            'update_env_var "$ROOT_ENV_FILE" "BLOCKCHAIN_SERVICES_ENABLED" "false"',
            'A Full-issued trust bundle is required in Lite mode.',
            'update_env_var "$ROOT_ENV_FILE" "LAB_ADMIN_BACKEND_URL" "$lab_admin_backend_url"',
        ),
        "windows": (
            'if not "!issuer_value!"=="" (',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_SERVICES_ENABLED" "false"',
            'A Full-issued trust bundle is required in Lite mode.',
            'call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_URL" "!lab_admin_backend_url!"',
        ),
        "compose": (
            'Embedded blockchain-services disabled (Lite mode); container is dormant.',
            'lite_mode=true',
            'ISSUER=${ISSUER:-}',
        ),
    },
}


OPTIONAL_PROFILE_CONTRACT = {
    "fmu-runner": {
        "shell": (
            'fmu_runner_profile="fmu-runner"',
            'compose_profiles="--profile $fmu_runner_profile"',
        ),
        "windows": (
            'set "fmu_runner_profile=fmu-runner"',
            'set "compose_full=!compose_full! --profile !fmu_runner_profile!"',
        ),
        "compose": ('fmu-runner:', 'profiles: ["fmu-runner"]'),
    },
    "fmu-local-dev": {
        "shell": (
            'fmu_runner_profile="fmu-local-dev"',
            'compose_profiles="--profile $fmu_runner_profile"',
        ),
        "windows": (
            'set "fmu_runner_profile=fmu-local-dev"',
            'set "compose_full=!compose_full! --profile !fmu_runner_profile!"',
        ),
        "compose": ('fmu-runner-local:', 'profiles: ["fmu-local-dev"]'),
    },
    "aas": {
        "shell": (
            'aas_bundled=true',
            'compose_profiles="--profile aas"',
        ),
        "windows": (
            'set "aas_enabled=1"',
            'set "compose_full=!compose_full! --profile aas"',
        ),
        "compose": (
            'basyx-aas-server:',
            'basyx-mongo:',
            'profiles: ["aas"]',
        ),
    },
    "certbot": {
        "shell": (
            'certbot_enabled=true',
            'compose_profiles="--profile certbot"',
        ),
        "windows": (
            'set "certbot_enabled=1"',
            'set "compose_full=!compose_full! --profile certbot"',
        ),
        "compose": (
            'certbot:',
            'certbot-renew:',
            'certbot-init:',
            'profiles: ["certbot"]',
        ),
    },
    "cloudflare_quick": {
        "shell": (
            'cf_profile="cloudflare"',
            'compose_profiles="--profile $cf_profile"',
        ),
        "windows": (
            'set "cf_profile=cloudflare"',
            'set "compose_full=!compose_full! --profile !cf_profile!"',
        ),
        "compose": ('cloudflared:', 'profiles: ["cloudflare"]'),
    },
    "cloudflare_token": {
        "shell": (
            'cf_profile="cloudflare-token"',
            'compose_profiles="--profile $cf_profile"',
        ),
        "windows": (
            'set "cf_profile=cloudflare-token"',
            'set "compose_full=!compose_full! --profile !cf_profile!"',
        ),
        "compose": ('cloudflared-token:', 'profiles: ["cloudflare-token"]'),
    },
}


def test_clean_install_matrix_covers_full_lite_and_remote_backend_modes():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    architecture_text = (ROOT / "docs" / "deployment-architectures.md").read_text(encoding="utf-8")

    for topology_name, contract in TOPOLOGY_CONTRACT.items():
        for marker in contract["shell"]:
            assert marker in shell_text, f"Missing shell topology marker: {topology_name}: {marker}"
        for marker in contract["windows"]:
            assert marker in windows_text, f"Missing Windows topology marker: {topology_name}: {marker}"
        for marker in contract["compose"]:
            assert marker in compose_text, f"Missing Compose topology marker: {topology_name}: {marker}"

    # The clean-install matrix is aligned with the documented control-plane
    # choices; standalone backend deployments are represented by Lite's remote
    # issuer/backend path and do not gain a local issuer accidentally.
    for architecture in (
        "Full only",
        "Lite only (with remote issuer)",
        "Full + N Lite",
        "`blockchain-services` + N Lite",
    ):
        assert architecture in architecture_text


def test_clean_install_matrix_keeps_optional_profiles_explicit_and_disjoint():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for profile_name, contract in OPTIONAL_PROFILE_CONTRACT.items():
        for marker in contract["shell"]:
            assert marker in shell_text, f"Missing shell profile marker: {profile_name}: {marker}"
        for marker in contract["windows"]:
            assert marker in windows_text, f"Missing Windows profile marker: {profile_name}: {marker}"
        for marker in contract["compose"]:
            assert marker in compose_text, f"Missing Compose profile marker: {profile_name}: {marker}"

    # A clean install selects one FMU backend profile through one variable;
    # the Compose file gives both services the same internal alias, so starting
    # both at once would violate the deployment contract.
    assert 'fmu_runner_profile="fmu-runner"' in shell_text
    assert 'fmu_runner_profile="fmu-local-dev"' in shell_text
    assert 'Do not start both FMU profiles' in (ROOT / "README.md").read_text(encoding="utf-8")


def test_clean_install_matrix_requires_validation_before_optional_startup():
    shell_text = SETUP_SH.read_text(encoding="utf-8")
    windows_text = SETUP_BAT.read_text(encoding="utf-8")

    for text, markers in (
        (
            shell_text,
            (
                'scripts/validate-gateway-env.py --env "$ROOT_ENV_FILE"',
                '\nsync_compose_secrets\n',
                'read -p "Do you want to start the services now? (Y/n): "',
                '$compose_full down --remove-orphans',
            ),
        ),
        (
            windows_text,
            (
                'Validate-GatewayEnv.ps1" -EnvPath "%ROOT_ENV_FILE%"',
                'call :SyncComposeSecrets',
                'set /p "start_services=Do you want to start the services now? (Y/n): "',
                'call !compose_full! down --remove-orphans',
            ),
        ),
    ):
        _assert_order(text, "clean install validation and startup", markers)

    assert 'set -euo pipefail' in shell_text
    assert 'if errorlevel 1 exit /b 1' in windows_text
