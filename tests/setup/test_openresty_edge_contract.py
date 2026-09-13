from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
OPENRESTY_ROOT = ROOT / "openresty"
ACCESS_CONF = OPENRESTY_ROOT / "lab_access.conf"
INTERNAL_HEALTH_INCLUDE = OPENRESTY_ROOT / "lab_access_health_internal.conf"
AUTH_HANDOFF_INCLUDE = OPENRESTY_ROOT / "lab_access_auth_handoff.conf"
GUACAMOLE_AUTH_INCLUDE = OPENRESTY_ROOT / "lab_access_guacamole_auth.conf"
GUACAMOLE_PROXY_INCLUDE = OPENRESTY_ROOT / "lab_access_guacamole_proxy.conf"
PROVISIONER_INCLUDE = OPENRESTY_ROOT / "lab_access_guacamole_provisioner.conf"
AAS_PUBLIC_INCLUDE = OPENRESTY_ROOT / "lab_access_aas_public.conf"
AAS_ADMIN_INCLUDE = OPENRESTY_ROOT / "lab_access_aas_admin.conf"
AAS_RESOLVE_INCLUDE = OPENRESTY_ROOT / "lab_access_aas_resolve.conf"
GATEWAY_MODE_INCLUDE = OPENRESTY_ROOT / "lab_access_gateway_mode.conf"
FMU_INCLUDE = OPENRESTY_ROOT / "lab_access_fmu.conf"
INIT_SSL = OPENRESTY_ROOT / "init-ssl.sh"
INIT_SSL_SECRETS = OPENRESTY_ROOT / "init-ssl-secrets.sh"
INIT_SSL_TLS = OPENRESTY_ROOT / "init-ssl-tls.sh"
INIT_SSL_JWT_SYNC = OPENRESTY_ROOT / "init-ssl-jwt-sync.sh"
INIT_SSL_JWT_WATCHERS = OPENRESTY_ROOT / "init-ssl-jwt-watchers.sh"


EXPECTED_LOCATION_MATRIX = (
    "/.well-known/pki-validation/",
    "= /.well-known/public-key.pem",
    "^~ /.well-known/acme-challenge/",
    "/",
    "/",
    "= /.well-known/public-key.pem",
    "= /lab-manager",
    "= /lab-manager/login",
    "= /lab-manager/access-policy",
    "/lab-manager/",
    "/lab-admin/",
    "/lab-content/",
    "= /access-audit/internal/session-observed",
    "= /reservations/projection",
    "/auth",
    "= /.well-known/openid-configuration",
    "= /wallet-dashboard",
    "= /wallet-dashboard/login",
    "/wallet-dashboard/",
    "= /institution-config",
    "= /institution-config/login",
    "= /admin/login",
    "= /admin/logout",
    "= /admin-login.html",
    "/institution-config/",
    "/billing/admin/",
    "/billing/",
    "/wallet/",
    "/onboarding/webauthn/",
    "= /intents",
    "/intents/",
    "= /ops/health",
    "= /ops/health/details",
    "/ops/",
    "= /health",
    "= /health/details",
    "= /gateway/health",
    "= /gateway/health/details",
    "/gateway/mode",
    "= /__health_blockchain",
    "= /__health_guacamole",
    "= /__health_guac_api",
    "= /__guacamole_tokens",
    "= /__health_ops",
    "= /__health_fmu_runner",
    "= /__health_aas",
    "= /auth/access",
    "= /auth/demo",
    "= /auth/fmu/revoke",
    "= /guacamole/api/tokens",
    "/guacamole/",
    "/aas/",
    "/gateway-provisioner/guacamole/",
    "/aas-admin/fmu/",
    "/aas-admin/lab/",
    "= /internal/aas-resolve",
    "/fmu/",
)

EXPECTED_INTERNAL_HEALTH_LOCATIONS = (
    "= /__health_blockchain",
    "= /__health_guacamole",
    "= /__health_guac_api",
    "= /__guacamole_tokens",
    "= /__health_ops",
    "= /__health_fmu_runner",
    "= /__health_aas",
)

EXPECTED_AUTH_HANDOFF_LOCATIONS = (
    "= /auth/access",
    "= /auth/demo",
    "= /auth/fmu/revoke",
)

EXPECTED_GUACAMOLE_AUTH_LOCATIONS = ("= /guacamole/api/tokens",)

EXPECTED_GUACAMOLE_PROXY_LOCATIONS = ("/guacamole/",)

EXPECTED_PROVISIONER_LOCATIONS = ("/gateway-provisioner/guacamole/",)

EXPECTED_AAS_PUBLIC_LOCATIONS = ("/aas/",)

EXPECTED_AAS_ADMIN_LOCATIONS = ("/aas-admin/fmu/", "/aas-admin/lab/")

EXPECTED_AAS_RESOLVE_LOCATIONS = ("= /internal/aas-resolve",)

EXPECTED_GATEWAY_MODE_LOCATIONS = ("/gateway/mode",)

EXPECTED_FMU_LOCATIONS = ("/fmu/",)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _location_signatures(conf: str) -> list[str]:
    pattern = re.compile(r"(?m)^[ \t]*location[ \t]+([^{}\r\n]+?)[ \t]*\{")
    return [match.group(1).strip() for match in pattern.finditer(conf)]


def _location_block(conf: str, signature: str, occurrence: int = 0) -> str:
    pattern = re.compile(
        rf"(?m)^[ \t]*location[ \t]+{re.escape(signature)}[ \t]*\{{"
    )
    matches = list(pattern.finditer(conf))
    if len(matches) <= occurrence:
        raise AssertionError(
            f"location {signature!r} occurrence {occurrence} was not found"
        )

    start = matches[occurrence].end()
    depth = 1
    position = start
    while position < len(conf):
        char = conf[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return conf[start : position - 1]
        position += 1
    raise AssertionError(f"location {signature!r} is not closed")


def _assert_order(block: str, first: str, second: str) -> None:
    first_position = block.find(first)
    second_position = block.find(second)
    assert first_position >= 0, f"missing directive: {first}"
    assert second_position >= 0, f"missing directive: {second}"
    assert first_position < second_position, f"{first!r} must precede {second!r}"


def test_lab_access_location_matrix_and_order_are_frozen():
    conf = _read(ACCESS_CONF)

    main_locations = tuple(_location_signatures(conf))
    health_locations = tuple(_location_signatures(_read(INTERNAL_HEALTH_INCLUDE)))
    auth_locations = tuple(_location_signatures(_read(AUTH_HANDOFF_INCLUDE)))
    guacamole_locations = tuple(
        _location_signatures(_read(GUACAMOLE_AUTH_INCLUDE))
    )
    guacamole_proxy_locations = tuple(
        _location_signatures(_read(GUACAMOLE_PROXY_INCLUDE))
    )
    provisioner_locations = tuple(
        _location_signatures(_read(PROVISIONER_INCLUDE))
    )
    aas_public_locations = tuple(
        _location_signatures(_read(AAS_PUBLIC_INCLUDE))
    )
    aas_admin_locations = tuple(
        _location_signatures(_read(AAS_ADMIN_INCLUDE))
    )
    aas_resolve_locations = tuple(
        _location_signatures(_read(AAS_RESOLVE_INCLUDE))
    )
    gateway_mode_locations = tuple(
        _location_signatures(_read(GATEWAY_MODE_INCLUDE))
    )
    fmu_locations = tuple(_location_signatures(_read(FMU_INCLUDE)))
    gateway_mode_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_GATEWAY_MODE_LOCATIONS[0]
    )
    health_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_INTERNAL_HEALTH_LOCATIONS[0]
    )
    auth_insertion = EXPECTED_LOCATION_MATRIX.index(EXPECTED_AUTH_HANDOFF_LOCATIONS[0])
    guacamole_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_GUACAMOLE_AUTH_LOCATIONS[0]
    )
    guacamole_proxy_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_GUACAMOLE_PROXY_LOCATIONS[0]
    )
    provisioner_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_PROVISIONER_LOCATIONS[0]
    )
    aas_public_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_AAS_PUBLIC_LOCATIONS[0]
    )
    aas_admin_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_AAS_ADMIN_LOCATIONS[0]
    )
    aas_resolve_insertion = EXPECTED_LOCATION_MATRIX.index(
        EXPECTED_AAS_RESOLVE_LOCATIONS[0]
    )
    fmu_insertion = EXPECTED_LOCATION_MATRIX.index(EXPECTED_FMU_LOCATIONS[0])
    expected_main_locations = (
        EXPECTED_LOCATION_MATRIX[:gateway_mode_insertion]
        + EXPECTED_LOCATION_MATRIX[
            gateway_mode_insertion + len(EXPECTED_GATEWAY_MODE_LOCATIONS) : health_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            health_insertion + len(EXPECTED_INTERNAL_HEALTH_LOCATIONS) : auth_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            auth_insertion + len(EXPECTED_AUTH_HANDOFF_LOCATIONS) : guacamole_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            guacamole_insertion + len(EXPECTED_GUACAMOLE_AUTH_LOCATIONS) : guacamole_proxy_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            guacamole_proxy_insertion + len(EXPECTED_GUACAMOLE_PROXY_LOCATIONS) : aas_public_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            aas_public_insertion + len(EXPECTED_AAS_PUBLIC_LOCATIONS) : provisioner_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            provisioner_insertion
            + len(EXPECTED_PROVISIONER_LOCATIONS) : aas_admin_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            aas_admin_insertion + len(EXPECTED_AAS_ADMIN_LOCATIONS) : aas_resolve_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            aas_resolve_insertion + len(EXPECTED_AAS_RESOLVE_LOCATIONS) :
            fmu_insertion
        ]
        + EXPECTED_LOCATION_MATRIX[
            fmu_insertion + len(EXPECTED_FMU_LOCATIONS) :
        ]
    )
    assert main_locations == expected_main_locations
    assert gateway_mode_locations == EXPECTED_GATEWAY_MODE_LOCATIONS
    assert health_locations == EXPECTED_INTERNAL_HEALTH_LOCATIONS
    assert auth_locations == EXPECTED_AUTH_HANDOFF_LOCATIONS
    assert guacamole_locations == EXPECTED_GUACAMOLE_AUTH_LOCATIONS
    assert guacamole_proxy_locations == EXPECTED_GUACAMOLE_PROXY_LOCATIONS
    assert provisioner_locations == EXPECTED_PROVISIONER_LOCATIONS
    assert aas_public_locations == EXPECTED_AAS_PUBLIC_LOCATIONS
    assert aas_admin_locations == EXPECTED_AAS_ADMIN_LOCATIONS
    assert aas_resolve_locations == EXPECTED_AAS_RESOLVE_LOCATIONS
    assert fmu_locations == EXPECTED_FMU_LOCATIONS
    effective_locations = (
        main_locations[:gateway_mode_insertion]
        + gateway_mode_locations
        + main_locations[gateway_mode_insertion:]
    )
    health_effective_insertion = health_insertion
    effective_locations = (
        effective_locations[:health_effective_insertion]
        + health_locations
        + effective_locations[health_effective_insertion:]
    )
    auth_effective_insertion = auth_insertion
    effective_locations = (
        effective_locations[:auth_effective_insertion]
        + auth_locations
        + effective_locations[auth_effective_insertion:]
    )
    effective_locations = (
        effective_locations[:guacamole_insertion]
        + guacamole_locations
        + effective_locations[guacamole_insertion:]
    )
    effective_locations = (
        effective_locations[:guacamole_proxy_insertion]
        + guacamole_proxy_locations
        + effective_locations[guacamole_proxy_insertion:]
    )
    effective_locations = (
        effective_locations[:aas_public_insertion]
        + aas_public_locations
        + effective_locations[aas_public_insertion:]
    )
    effective_locations = (
        effective_locations[:provisioner_insertion]
        + provisioner_locations
        + effective_locations[provisioner_insertion:]
    )
    effective_locations = (
        effective_locations[:aas_admin_insertion]
        + aas_admin_locations
        + effective_locations[aas_admin_insertion:]
    )
    effective_locations = (
        effective_locations[:aas_resolve_insertion]
        + aas_resolve_locations
        + effective_locations[aas_resolve_insertion:]
    )
    effective_locations = (
        effective_locations[:fmu_insertion]
        + fmu_locations
        + effective_locations[fmu_insertion:]
    )
    assert effective_locations == EXPECTED_LOCATION_MATRIX

    lab_admin = _location_block(conf, "/lab-admin/")
    _assert_order(
        lab_admin,
        "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;",
        "proxy_pass $backend_lab_admin;",
    )
    _assert_order(
        lab_admin,
        "proxy_set_header Origin \"\";",
        "proxy_pass $backend_lab_admin;",
    )

    fmu = _location_block(_read(FMU_INCLUDE), "/fmu/")
    _assert_order(fmu, "limit_req zone=fmu_api", "access_by_lua_file")
    _assert_order(fmu, "access_by_lua_file /etc/openresty/lua/fmu_access.lua;", "proxy_pass")

    aas_admin = _location_block(_read(AAS_ADMIN_INCLUDE), "/aas-admin/lab/")
    _assert_order(
        aas_admin,
        "rewrite_by_lua_block",
        "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;",
    )
    _assert_order(
        aas_admin,
        'proxy_set_header Authorization "";',
        "proxy_pass $ops_upstream;",
    )


def test_gateway_mode_route_keeps_public_full_lite_payload_and_options():
    conf = _read(ACCESS_CONF)
    include = _read(GATEWAY_MODE_INCLUDE)
    include_line = "include /etc/openresty/lab_access_gateway_mode.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_GATEWAY_MODE_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "/gateway/mode")
    assert "if ($request_method = 'OPTIONS')" in block
    assert "return 204;" in block
    assert 'local lite_mode = ngx.shared.config:get("lite_mode")' in block
    assert 'local mode = "full"' in block
    assert 'mode = "lite"' in block
    assert 'ngx.header["Content-Type"] = "application/json"' in block
    assert "{\"mode\":\"%s\",\"lite\":%s}" in block
    assert "proxy_pass" not in block
    assert "access_by_lua" not in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_gateway_mode.conf "
        "/etc/openresty/lab_access_gateway_mode.conf"
    ) in dockerfile


def test_public_and_internal_health_routes_keep_their_security_boundaries():
    conf = _read(ACCESS_CONF)
    effective_conf = conf + "\n" + _read(INTERNAL_HEALTH_INCLUDE)

    for signature in ("= /health", "= /ops/health", "= /gateway/health"):
        block = _location_block(effective_conf, signature)
        assert "content_by_lua_file /etc/openresty/lua/public_health.lua;" in block
        assert "access_by_lua_file" not in block

    for signature in ("= /health/details", "= /ops/health/details", "= /gateway/health/details"):
        block = _location_block(effective_conf, signature)
        assert (
            "access_by_lua_file /etc/openresty/lua/health_details_access.lua;"
            in block
        )

    for signature in (
        "= /__health_blockchain",
        "= /__health_guacamole",
        "= /__health_guac_api",
        "= /__guacamole_tokens",
        "= /__health_ops",
        "= /__health_fmu_runner",
        "= /__health_aas",
    ):
        assert "internal;" in _location_block(effective_conf, signature)


def test_internal_health_routes_are_included_inside_the_https_server():
    conf = _read(ACCESS_CONF)
    include = _read(INTERNAL_HEALTH_INCLUDE)
    include_line = "include /etc/openresty/lab_access_health_internal.conf;"

    assert conf.count(include_line) == 1
    assert include.count("location = ") == len(EXPECTED_INTERNAL_HEALTH_LOCATIONS)
    assert "listen 443 ssl;" in conf
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    expected_upstreams = {
        "= /__health_blockchain": "proxy_set_header Host blockchain-services;",
        "= /__health_guacamole": "proxy_set_header Host guacamole;",
        "= /__health_guac_api": "proxy_set_header Host guacamole;",
        "= /__guacamole_tokens": "proxy_set_header Host guacamole;",
        "= /__health_ops": "proxy_set_header Host ops-worker;",
        "= /__health_fmu_runner": "proxy_set_header Host fmu-runner;",
        "= /__health_aas": "access_by_lua_file /etc/openresty/lua/aas_access.lua;",
    }
    for signature, directive in expected_upstreams.items():
        block = _location_block(include, signature)
        assert "internal;" in block
        assert directive in block
        assert "proxy_pass" in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_health_internal.conf "
        "/etc/openresty/lab_access_health_internal.conf"
    ) in dockerfile


def test_auth_handoff_routes_are_included_without_changing_their_contract():
    conf = _read(ACCESS_CONF)
    include = _read(AUTH_HANDOFF_INCLUDE)
    include_line = "include /etc/openresty/lab_access_auth_handoff.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_AUTH_HANDOFF_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    expected_handlers = {
        "= /auth/access": (
            "add_header Referrer-Policy no-referrer always;",
            "content_by_lua_file /etc/openresty/lua/access_code_exchange.lua;",
        ),
        "= /auth/demo": (
            "add_header Cache-Control \"no-store\" always;",
            "content_by_lua_file /etc/openresty/lua/demo_access_exchange.lua;",
        ),
        "= /auth/fmu/revoke": (
            "add_header Cache-Control \"no-store\" always;",
            "content_by_lua_file /etc/openresty/lua/fmu_session_revoke.lua;",
        ),
    }
    for signature, directives in expected_handlers.items():
        block = _location_block(include, signature)
        assert "access_log off;" in block
        for directive in directives:
            assert directive in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_auth_handoff.conf "
        "/etc/openresty/lab_access_auth_handoff.conf"
    ) in dockerfile


def test_guacamole_token_route_is_included_with_login_limits_intact():
    conf = _read(ACCESS_CONF)
    include = _read(GUACAMOLE_AUTH_INCLUDE)
    include_line = "include /etc/openresty/lab_access_guacamole_auth.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_GUACAMOLE_AUTH_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "= /guacamole/api/tokens")
    assert "limit_req zone=guac_token_login_ip burst=5 nodelay;" in block
    assert "limit_req_status 429;" in block
    assert "access_by_lua_file /etc/openresty/lua/access.lua;" in block
    assert (
        "content_by_lua_file /etc/openresty/lua/guacamole_token_exchange.lua;"
        in block
    )
    assert "client_max_body_size 5M;" in block
    assert "access_log off;" in block
    assert "internal;" not in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_guacamole_auth.conf "
        "/etc/openresty/lab_access_guacamole_auth.conf"
    ) in dockerfile


def test_guacamole_websocket_proxy_keeps_hooks_headers_and_timeouts():
    conf = _read(ACCESS_CONF)
    include = _read(GUACAMOLE_PROXY_INCLUDE)
    include_line = "include /etc/openresty/lab_access_guacamole_proxy.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_GUACAMOLE_PROXY_LOCATIONS
    token_include_line = "include /etc/openresty/lab_access_guacamole_auth.conf;"
    aas_public_include_line = "include /etc/openresty/lab_access_aas_public.conf;"
    assert conf.index(token_include_line) < conf.index(include_line)
    assert conf.index(include_line) < conf.index(aas_public_include_line)

    block = _location_block(include, "/guacamole/")
    for directive in (
        "access_by_lua_file /etc/openresty/lua/access.lua;",
        "header_filter_by_lua_file /etc/openresty/lua/header_filter.lua;",
        "log_by_lua_file /etc/openresty/lua/log.lua;",
        "proxy_set_header Host $http_host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_set_header Upgrade $http_upgrade;",
        "proxy_set_header Connection $connection_upgrade;",
        'proxy_set_header Keep-Alive "";',
        'proxy_set_header Proxy-Connection "";',
        'proxy_set_header TE "";',
        'proxy_set_header Trailer "";',
        'proxy_set_header Accept-Encoding "";',
        "proxy_redirect off;",
        "proxy_buffering off;",
        "proxy_read_timeout 600s;",
        "proxy_connect_timeout 600s;",
        "proxy_send_timeout 600s;",
        "proxy_http_version 1.1;",
        "client_max_body_size 5M;",
        "access_log off;",
        "resolver 127.0.0.11 valid=5s;",
        "set $backend_guacamole http://guacamole:8080;",
        "proxy_pass $backend_guacamole;",
    ):
        assert directive in block
    _assert_order(
        block,
        "access_by_lua_file /etc/openresty/lua/access.lua;",
        "header_filter_by_lua_file /etc/openresty/lua/header_filter.lua;",
    )
    _assert_order(
        block,
        "header_filter_by_lua_file /etc/openresty/lua/header_filter.lua;",
        "log_by_lua_file /etc/openresty/lua/log.lua;",
    )
    _assert_order(block, "log_by_lua_file /etc/openresty/lua/log.lua;", "proxy_pass")

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_guacamole_proxy.conf "
        "/etc/openresty/lab_access_guacamole_proxy.conf"
    ) in dockerfile


def test_guacamole_provisioner_route_keeps_token_guard_and_rewrite():
    conf = _read(ACCESS_CONF)
    include = _read(PROVISIONER_INCLUDE)
    include_line = "include /etc/openresty/lab_access_guacamole_provisioner.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_PROVISIONER_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "/gateway-provisioner/guacamole/")
    assert "access_by_lua_block" in block
    assert 'os.getenv("GUACAMOLE_PROVISIONER_TOKEN")' in block
    assert 'os.getenv("LAB_MANAGER_TOKEN")' in block
    assert 'os.getenv("GUACAMOLE_PROVISIONER_TOKEN_HEADER")' in block
    assert '"X-Guacamole-Provisioner-Token"' in block
    assert '"X-Lab-Manager-Token"' in block
    assert 'ngx.HTTP_UNAUTHORIZED' in block
    assert '{"success":false,"error":"Unauthorized"}' in block
    for directive in (
        "proxy_set_header Host ops-worker;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_read_timeout 10s;",
        "proxy_connect_timeout 3s;",
        "proxy_send_timeout 10s;",
        "resolver 127.0.0.11 valid=30s ipv6=off;",
        "set $backend_ops_worker http://ops-worker:8081;",
        "rewrite ^/gateway-provisioner/guacamole/(.*)$ /internal/guacamole/$1 break;",
        "proxy_pass $backend_ops_worker;",
    ):
        assert directive in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_guacamole_provisioner.conf "
        "/etc/openresty/lab_access_guacamole_provisioner.conf"
    ) in dockerfile


def test_aas_public_route_keeps_read_only_policy_and_upstream_resolution():
    conf = _read(ACCESS_CONF)
    include = _read(AAS_PUBLIC_INCLUDE)
    include_line = "include /etc/openresty/lab_access_aas_public.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_AAS_PUBLIC_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "/aas/")
    assert "access_by_lua_file /etc/openresty/lua/aas_access.lua;" in block
    assert "rewrite_by_lua_block" in block
    assert 'require("aas_link_resolver")' in block
    assert "resolver.rewrite_if_linked()" in block
    assert "if ($request_method !~ ^(GET|HEAD|OPTIONS)$)" in block
    assert 'return 405;' in block
    assert 'if ($cors_allow_origin = "DENY")' in block
    assert "return 403;" in block
    assert "if ($request_method = 'OPTIONS')" in block
    assert "return 204;" in block
    for directive in (
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_read_timeout 15s;",
        "proxy_connect_timeout 5s;",
        "proxy_send_timeout 10s;",
        "resolver 127.0.0.11 valid=30s ipv6=off;",
        "set_by_lua_block $basyx_upstream",
        'return config:get("basyx_aas_url") or "http://basyx-aas-server:8081"',
        "rewrite ^/aas/(.*)$ /$1 break;",
        "proxy_pass $basyx_upstream;",
    ):
        assert directive in block
    assert block.index("rewrite_by_lua_block") < block.index("proxy_pass")

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_aas_public.conf "
        "/etc/openresty/lab_access_aas_public.conf"
    ) in dockerfile


def test_aas_admin_routes_keep_full_lite_guards_auth_and_destinations():
    conf = _read(ACCESS_CONF)
    include = _read(AAS_ADMIN_INCLUDE)
    include_line = "include /etc/openresty/lab_access_aas_admin.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_AAS_ADMIN_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    fmu_block = _location_block(include, "/aas-admin/fmu/")
    assert "rewrite_by_lua_block" in fmu_block
    assert 'local lite_mode = ngx.shared.config:get("lite_mode")' in fmu_block
    assert "Forbidden: AAS endpoints are not available in Lite mode." in fmu_block
    assert "local fmu_runner_enabled = ngx.shared.config:get(\"fmu_runner_enabled\")" in fmu_block
    assert "Service unavailable: FMU runner integration is disabled on this gateway." in fmu_block
    assert "return ngx.exit(503)" in fmu_block
    assert "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;" in fmu_block
    for directive in (
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_read_timeout 60s;",
        "proxy_connect_timeout 10s;",
        "proxy_send_timeout 30s;",
        "client_max_body_size 50M;",
        "resolver 127.0.0.11 valid=30s ipv6=off;",
        "set $fmu_runner_upstream http://fmu-runner:8090;",
        "proxy_pass $fmu_runner_upstream;",
    ):
        assert directive in fmu_block
    _assert_order(
        fmu_block,
        "rewrite_by_lua_block",
        "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;",
    )

    lab_block = _location_block(include, "/aas-admin/lab/")
    assert "rewrite_by_lua_block" in lab_block
    assert 'local lite_mode = ngx.shared.config:get("lite_mode")' in lab_block
    assert "Forbidden: AAS endpoints are not available in Lite mode." in lab_block
    assert "fmu_runner_enabled" not in lab_block
    assert "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;" in lab_block
    for directive in (
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        'proxy_set_header Authorization "";',
        'proxy_set_header Cookie "";',
        'proxy_set_header X-Lab-Manager-Token "";',
        "proxy_read_timeout 30s;",
        "proxy_connect_timeout 10s;",
        "proxy_send_timeout 15s;",
        "client_max_body_size 10M;",
        "resolver 127.0.0.11 valid=30s ipv6=off;",
        "set $ops_upstream http://ops-worker:8081;",
        "proxy_pass $ops_upstream;",
    ):
        assert directive in lab_block
    _assert_order(
        lab_block,
        "rewrite_by_lua_block",
        "access_by_lua_file /etc/openresty/lua/lab_manager_admin_access.lua;",
    )
    _assert_order(
        lab_block,
        'proxy_set_header Authorization "";',
        "proxy_pass $ops_upstream;",
    )

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_aas_admin.conf "
        "/etc/openresty/lab_access_aas_admin.conf"
    ) in dockerfile


def test_aas_resolve_subrequest_keeps_internal_fmu_gate_and_proxy_contract():
    conf = _read(ACCESS_CONF)
    include = _read(AAS_RESOLVE_INCLUDE)
    include_line = "include /etc/openresty/lab_access_aas_resolve.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_AAS_RESOLVE_LOCATIONS
    assert conf.index("listen 443 ssl;") < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "= /internal/aas-resolve")
    assert "internal;" in block
    assert "if ($fmu_runner_enabled = 0)" in block
    assert "return 503;" in block
    assert "proxy_pass_request_headers off;" in block
    assert "proxy_read_timeout 2s;" in block
    assert "proxy_connect_timeout 1s;" in block
    assert "proxy_send_timeout 1s;" in block
    assert "resolver 127.0.0.11 valid=30s ipv6=off;" in block
    assert "set $fmu_resolve_upstream http://fmu-runner:8090/aas-admin/resolve-aas-id;" in block
    assert "proxy_pass $fmu_resolve_upstream;" in block

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_aas_resolve.conf "
        "/etc/openresty/lab_access_aas_resolve.conf"
    ) in dockerfile


def test_fmu_route_keeps_availability_limits_cors_auth_and_proxy_contract():
    conf = _read(ACCESS_CONF)
    include = _read(FMU_INCLUDE)
    include_line = "include /etc/openresty/lab_access_fmu.conf;"
    aas_resolve_include_line = "include /etc/openresty/lab_access_aas_resolve.conf;"

    assert conf.count(include_line) == 1
    assert tuple(_location_signatures(include)) == EXPECTED_FMU_LOCATIONS
    assert conf.index(aas_resolve_include_line) < conf.index(include_line)
    assert conf.index(include_line) < conf.rindex("\n}")

    block = _location_block(include, "/fmu/")
    assert "if ($fmu_runner_enabled = 0)" in block
    assert "add_header Content-Type text/plain;" in block
    assert (
        'return 503 "Service unavailable: FMU runner integration is disabled on this gateway.\\n";'
        in block
    )
    assert "limit_req zone=fmu_api burst=20 nodelay;" in block
    assert "limit_req_status 429;" in block
    assert "access_by_lua_file /etc/openresty/lua/fmu_access.lua;" in block
    assert block.count('if ($cors_allow_origin = "DENY")') == 2
    assert block.count("return 403;") >= 2
    assert "if ($request_method = 'OPTIONS')" in block
    for directive in (
        "add_header 'Access-Control-Allow-Origin' $cors_allow_origin always;",
        "add_header 'Access-Control-Allow-Credentials' 'true' always;",
        "add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;",
        "add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With' always;",
        "add_header 'Access-Control-Expose-Headers' 'Content-Disposition' always;",
        "add_header 'Access-Control-Max-Age' 1728000 always;",
        "add_header 'Vary' 'Origin' always;",
        "proxy_set_header Host $http_host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_set_header Authorization $http_authorization;",
        "proxy_set_header Upgrade $http_upgrade;",
        'proxy_set_header Connection "upgrade";',
        "proxy_redirect off;",
        "proxy_buffering off;",
        "proxy_read_timeout 600s;",
        "proxy_connect_timeout 30s;",
        "proxy_send_timeout 600s;",
        "proxy_http_version 1.1;",
        "client_max_body_size 10M;",
        "resolver 127.0.0.11 valid=30s ipv6=off;",
        "set $fmu_upstream http://fmu-runner:8090;",
        "rewrite ^/fmu/(.*)$ /$1 break;",
        "proxy_pass $fmu_upstream;",
    ):
        assert directive in block
    _assert_order(block, "if ($fmu_runner_enabled = 0)", "limit_req zone=fmu_api")
    _assert_order(block, "limit_req zone=fmu_api", "access_by_lua_file")
    _assert_order(
        block,
        "access_by_lua_file /etc/openresty/lua/fmu_access.lua;",
        'if ($cors_allow_origin = "DENY")',
    )
    _assert_order(block, 'if ($request_method = \'OPTIONS\')', "proxy_pass")

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert (
        "COPY lab_access_fmu.conf "
        "/etc/openresty/lab_access_fmu.conf"
    ) in dockerfile


def test_tls_and_public_key_configuration_remain_pinned():
    conf = _read(ACCESS_CONF)

    assert "listen 443 ssl;" in conf
    assert "http2 on;" in conf
    assert "ssl_certificate /etc/ssl/private/fullchain.pem;" in conf
    assert "ssl_certificate_key /etc/ssl/private/privkey.pem;" in conf
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in conf
    assert "Strict-Transport-Security" in conf
    assert "Content-Security-Policy \"default-src 'self';" in conf

    public_key_locations = [
        _location_block(conf, "= /.well-known/public-key.pem", occurrence)
        for occurrence in range(2)
    ]
    for block in public_key_locations:
        assert "content_by_lua_block" in block
        assert "/etc/ssl/private/public_key.pem" in block
        assert "/etc/openresty/jwt-keys/public_key.pem" in block
        assert "ngx.exit(404)" in block


def test_init_ssl_preserves_secret_loading_tls_validation_and_mode_split():
    script = _read(INIT_SSL)
    secrets_script = _read(INIT_SSL_SECRETS)
    tls_script = _read(INIT_SSL_TLS)
    jwt_sync_script = _read(INIT_SSL_JWT_SYNC)

    expected_secrets = (
        "admin_access_token",
        "lab_manager_token",
        "ops_internal_auth_token",
        "guac_admin_pass",
        "auth_access_code_redeemer_token",
        "session_observation_ingest_token",
        "guacamole_provisioner_token",
        "aas_service_token",
        "lab_admin_backend_token",
    )
    for secret in expected_secrets:
        variable = secret.upper()
        assert f"load_secret_env {variable} /run/secrets/{secret}" in secrets_script

    source_line = ". /usr/local/bin/init-ssl-secrets.sh"
    assert source_line in script
    assert script.index(source_line) < script.index('echo "=== OpenResty SSL Certificate Check ==="')
    assert "load_secret_env " not in script
    assert "load_secret_env() {" in secrets_script

    tls_source_line = ". /usr/local/bin/init-ssl-tls.sh"
    assert tls_source_line in script
    assert script.index("set_ssl_permissions() {") < script.index(tls_source_line)
    assert script.index(tls_source_line) < script.index("if cert_pair_is_usable")
    assert "atomic_tls_copy() {" not in script
    assert "cert_pair_is_usable() {" not in script
    assert "install_tls_pair() {" not in script
    assert "atomic_tls_copy() {" in tls_script
    assert "cert_pair_is_usable() {" in tls_script
    assert "install_tls_pair() {" in tls_script
    assert "openssl x509 -in \"$cert_path\" -checkend 0 -noout" in tls_script
    assert "cmp -s \"$cert_public_tmp\" \"$key_public_tmp\"" in tls_script
    assert "atomic_tls_copy \"$source_cert\" \"$CERT_FILE\" 0644" in tls_script
    assert "atomic_tls_copy \"$source_key\" \"$KEY_FILE\" 0640" in tls_script

    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")
    assert "COPY init-ssl-secrets.sh /usr/local/bin/init-ssl-secrets.sh" in dockerfile
    assert "COPY init-ssl-tls.sh /usr/local/bin/init-ssl-tls.sh" in dockerfile

    jwt_source_line = ". /usr/local/bin/init-ssl-jwt-sync.sh"
    assert jwt_source_line in script
    assert script.index("atomic_copy() {") < script.index(jwt_source_line)
    assert script.index(jwt_source_line) < script.index("primary_certbot_domain() {")
    assert "build_key_url_from_issuer() {" not in script
    assert "sync_jwt_public_key_from_issuer() {" not in script
    assert "build_key_url_from_issuer() {" in jwt_sync_script
    assert "sync_jwt_public_key_from_issuer() {" in jwt_sync_script
    assert "JWT_PUBLIC_KEY}.download" in jwt_sync_script
    assert "BEGIN PUBLIC KEY" in jwt_sync_script
    assert 'openssl pkey -pubin -in "$tmp_key" -noout' in jwt_sync_script
    assert 'JWT_PREVIOUS_PUBLIC_KEY"' in jwt_sync_script
    assert 'JWT_PREVIOUS_ISSUED_MARKER"' in jwt_sync_script
    assert 'JWT_ACTIVE_SNAPSHOT"' in jwt_sync_script
    assert "COPY init-ssl-jwt-sync.sh /usr/local/bin/init-ssl-jwt-sync.sh" in dockerfile

    assert 'SSL_DIR="/etc/ssl/private"' in script
    assert 'CERT_FILE="$SSL_DIR/fullchain.pem"' in script
    assert 'KEY_FILE="$SSL_DIR/privkey.pem"' in script
    assert "cert_pair_is_usable" in script

    assert 'FULL_JWT_PUBLIC_KEY="/etc/openresty/jwt-keys/public_key.pem"' in script
    assert 'REMOTE_JWT_PUBLIC_KEY="$SSL_DIR/public_key.pem"' in script
    assert 'JWT_KEY_CONTEXT="$SSL_DIR/.jwt-key-context"' in script
    assert 'jwt_key_sync_mode="local"' in script
    assert 'jwt_key_sync_mode="remote"' in script
    assert 'if [ -n "$ISSUER_OVERRIDE" ]' in script
    assert "sync_jwt_public_key_from_issuer" in script
    assert "watch_certs &" in script
    assert "watch_full_jwt_public_key &" in script
    assert "auto_rotate_self_signed &" in script
    assert "openresty -s reload" in script
    assert not re.search(
        r"(?m)^\s*(?:openssl|cp|mv|install)[^\n]*private_key\.pem",
        script,
    )


def test_init_ssl_jwt_watchers_keep_mode_guards_and_launch_order():
    script = _read(INIT_SSL)
    watchers = _read(INIT_SSL_JWT_WATCHERS)
    dockerfile = _read(OPENRESTY_ROOT / "Dockerfile")

    source_line = ". /usr/local/bin/init-ssl-jwt-watchers.sh"
    snapshot_anchor = (
        'if [ "$jwt_key_sync_mode" = "local" ] && '
        'is_valid_public_key "$FULL_JWT_PUBLIC_KEY"; then'
    )
    assert source_line in script
    assert script.index(snapshot_anchor) < script.index(source_line)
    assert script.index(source_line) < script.index('echo "=== Starting OpenResty ==="')

    for function_name in (
        "retire_previous_jwt_key",
        "watch_full_jwt_public_key",
        "auto_refresh_jwt_public_key",
    ):
        signature = f"{function_name}() {{"
        assert signature not in script
        assert signature in watchers

    assert 'if [ "$jwt_key_sync_mode" != "local" ]; then' in watchers
    assert 'if [ "$jwt_key_sync_mode" != "remote" ]; then' in watchers
    assert 'JWT_KEY_OVERLAP_SECONDS' in watchers
    assert 'JWT_KEY_REFRESH_INTERVAL_SECONDS' in watchers
    assert 'JWT_PREVIOUS_ISSUED_MARKER' in watchers
    assert 'JWT_PREVIOUS_PUBLIC_KEY' in watchers
    assert 'JWT_ACTIVE_SNAPSHOT' in watchers
    assert 'FULL_JWT_PUBLIC_KEY' in watchers
    assert 'atomic_copy "$JWT_ACTIVE_SNAPSHOT" "$JWT_PREVIOUS_PUBLIC_KEY"' in watchers
    assert 'atomic_copy "$FULL_JWT_PUBLIC_KEY" "$JWT_ACTIVE_SNAPSHOT"' in watchers
    assert 'openresty -s reload' in watchers
    assert 'watch_full_jwt_public_key &' not in watchers
    assert 'auto_refresh_jwt_public_key &' not in watchers

    launch_order = (
        script.index("watch_certs &"),
        script.index("watch_full_jwt_public_key &"),
        script.index("auto_rotate_self_signed &"),
        script.index("auto_refresh_jwt_public_key &"),
    )
    assert launch_order == tuple(sorted(launch_order))
    assert "COPY init-ssl-jwt-watchers.sh /usr/local/bin/init-ssl-jwt-watchers.sh" in dockerfile
