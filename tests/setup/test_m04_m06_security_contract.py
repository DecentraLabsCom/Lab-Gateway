from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_guacamole_manual_login_has_ip_and_user_rate_limits():
    nginx = (ROOT / "openresty" / "nginx.conf").read_text(encoding="utf-8")
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
    guard = (ROOT / "openresty" / "lua" / "modules" / "guacamole_login_guard.lua").read_text(encoding="utf-8")
    dockerfile = (ROOT / "guacamole" / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "guacamole" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "zone=guac_token_login_ip" in nginx
    assert "location = /guacamole/api/tokens" in conf
    assert "limit_req zone=guac_token_login_ip" in conf
    assert "lua_shared_dict guac_login_rate" in nginx
    assert "get_post_args" in guard
    assert "HTTP_TOO_MANY_REQUESTS" in guard
    assert "GUACAMOLE_BAN_SHA256" in dockerfile
    assert "guacamole-auth-ban-${GUACAMOLE_VERSION}.jar" in dockerfile
    assert "ban-max-invalid-attempts" in entrypoint
    assert "BAN_MAX_INVALID_ATTEMPTS" in compose
    assert "GUACAMOLE_LOGIN_RATE_LIMIT_PER_MINUTE=10" in env_example
    assert "BAN_ADDRESS_DURATION=300" in env_example


def test_fmu_auth_requires_issuer_and_bearer_only():
    auth = (ROOT / "fmu-runner" / "auth.py").read_text(encoding="utf-8")
    realtime = (ROOT / "fmu-runner" / "realtime_ws.py").read_text(encoding="utf-8")
    station = (ROOT / "fmu-runner" / "station_ws_proxy.py").read_text(encoding="utf-8")

    assert "_build_local_issuer" in auth
    assert '"require": ["exp", "iat", "iss"]' in auth
    assert 'query_params.get("token")' not in realtime
    assert 'query_params.get("token")' not in station
    assert 'cookie_name in ("token", "jwt", "jti", "JTI")' not in auth
    assert 'cookie_name in ("token", "jwt", "jti", "JTI")' not in realtime
    assert 'cookie_name in ("token", "jwt", "jti", "JTI")' not in station


def test_secrets_are_not_shared_with_backend_or_printed_as_urls():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    setup_sh = (ROOT / "setup.sh").read_text(encoding="utf-8")
    setup_bat = (ROOT / "setup.bat").read_text(encoding="utf-8")

    assert "      - .env  # Main gateway configuration" not in compose
    assert "umask 077" in setup_sh
    assert 'chmod 600 "$ROOT_ENV_FILE" "$BLOCKCHAIN_ENV_FILE"' in setup_sh
    assert ":SecureEnvFile" in setup_bat
    assert "icacls" in setup_bat
    assert "wallet-dashboard?token=" not in setup_sh
    assert "wallet-dashboard?token=" not in setup_bat
