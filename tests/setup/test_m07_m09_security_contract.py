from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_aas_profile_isolated_and_authenticated():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "openresty" / "nginx.conf").read_text(encoding="utf-8")
    aas_access = (ROOT / "openresty" / "lua" / "aas_access.lua").read_text(encoding="utf-8")
    mongo_init = (ROOT / "basyx-mongo" / "init-user.js").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    setup_sh = (ROOT / "setup.sh").read_text(encoding="utf-8")
    setup_bat = (ROOT / "setup.bat").read_text(encoding="utf-8")

    assert "fmu_aas:" in compose and "internal: true" in compose
    assert "aas_data:" in compose
    assert "labels: \"service=ops-worker\"" in compose
    assert "- fmu_aas" in compose
    assert "mongod --auth" in compose
    assert "authSource=basyx" in compose
    assert "01-create-aas-user.js" in compose
    assert "BASYX_MONGO_USER" in mongo_init and "readWrite" in mongo_init
    assert "MONGO_INITDB_ROOT_PASSWORD" in mongo_init
    assert "env AAS_ALLOWED_HOSTS;" in nginx
    assert "env AAS_SERVICE_TOKEN;" in nginx
    assert "external AAS endpoint must use HTTPS" in aas_access
    assert "AAS_ALLOWED_HOSTS" in aas_access
    assert "AAS_SERVICE_TOKEN" in aas_access
    assert 'ngx.req.set_header("Authorization", nil)' in aas_access
    assert "AAS_ALLOWED_HOSTS=" in env
    assert "AAS_SERVICE_TOKEN_HEADER=Authorization" in env
    assert "AAS_ALLOWED_HOSTS" in setup_sh and "AAS_SERVICE_TOKEN" in setup_sh
    assert "AAS_ALLOWED_HOSTS" in setup_bat and "AAS_SERVICE_TOKEN" in setup_bat


def test_external_aas_policy_is_applied_to_proxy_and_workers():
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
    ops = (ROOT / "ops-worker" / "aas_generator.py").read_text(encoding="utf-8")
    fmu = (ROOT / "fmu-runner" / "aas_generator.py").read_text(encoding="utf-8")

    assert "location /aas/" in conf
    assert "access_by_lua_file /etc/openresty/lua/aas_access.lua;" in conf
    assert "location = /__health_aas" in conf
    assert "headers=_aas_request_headers()" in fmu
    assert "session.headers.update({\"Content-Type\": \"application/json\", **_aas_request_headers()})" in ops
    assert "external AAS endpoint must use HTTPS" in ops
    assert "external AAS endpoint must use HTTPS" in fmu


def test_demo_guard_is_session_scoped_and_fail_closed():
    guard = (ROOT / "openresty" / "lua" / "modules" / "demo_guard.lua").read_text(encoding="utf-8")
    handoff = (ROOT / "openresty" / "lua" / "modules" / "demo_handoff.lua").read_text(encoding="utf-8")
    log_handler = (ROOT / "openresty" / "lua" / "modules" / "log_handler.lua").read_text(encoding="utf-8")
    nginx = (ROOT / "openresty" / "nginx.conf").read_text(encoding="utf-8")

    assert "session:" in guard
    assert "jwt_jti" in guard
    assert "availability authority unavailable" in guard
    assert "/api/demo/eligibility" in guard
    assert "body.eligible" in guard
    assert "canonical_lab_id" in guard
    assert "arg_labId" in handoff
    assert "requested_lab_id ~= configured_lab_id" in handoff
    assert "Demo availability cannot be verified" in guard
    assert "function _M.release" in guard
    assert "demo_guard.release" in log_handler
    assert "lua_shared_dict demo_sessions" in nginx


def test_demo_guacamole_principal_is_managed_and_reconciled_fail_closed():
    reconciler = (ROOT / "mysql" / "000-ensure-user.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    setup_sh = (ROOT / "setup.sh").read_text(encoding="utf-8")
    setup_bat = (ROOT / "setup.bat").read_text(encoding="utf-8")
    demo_section = reconciler.split("# ── Demo Guacamole principal", 1)[1]

    # The demo account is platform-owned, so a pre-existing account must be
    # proven to carry the platform marker before it can be reconciled.
    assert "guacamole_user_attribute" in demo_section
    assert "DEMO_LAB_ID" in demo_section
    assert "decentralabs_demo_lab_id" in demo_section
    assert "collision" in demo_section.lower()
    assert "INSERT IGNORE" not in demo_section

    # A demo principal must have no inherited or non-connection privileges.
    for table in (
        "guacamole_connection_permission",
        "guacamole_connection_group_permission",
        "guacamole_sharing_profile_permission",
        "guacamole_system_permission",
        "guacamole_user_permission",
        "guacamole_user_group_permission",
        "guacamole_user_group_member",
    ):
        assert f"{table}" in demo_section

    # Creation and permission reconciliation are guarded by database state,
    # including the configured connection and the affected-row result.
    assert "ROW_COUNT()" in demo_section
    assert "does not exist" in demo_section
    assert "exactly one READ permission" in demo_section
    assert "DEMO_LAB_ID: ${DEMO_LAB_ID:-}" in compose
    assert 'demo_user="demo-lab-${demo_lab_id}"' in setup_sh
    assert 'set "demo_user=demo-lab-!demo_lab_id!"' in setup_bat


def test_cors_denied_preflight_is_not_reflected():
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")

    assert "set $cors_preflight_origin $http_origin;" not in conf
    for location in ("location /auth", "location /aas/", "location /fmu/"):
        start = conf.index(location)
        end = conf.find("\n    location ", start + len(location))
        block = conf[start:] if end == -1 else conf[start:end]
        assert 'if ($cors_allow_origin = "DENY")' in block
        assert "return 403;" in block
        assert "if ($request_method = 'OPTIONS')" in block
