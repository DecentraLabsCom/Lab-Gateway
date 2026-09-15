from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_admin_bootstrap_is_post_only_and_cookies_are_path_scoped():
    openresty_root = ROOT / "openresty"
    conf = "\n".join(
        (openresty_root / name).read_text(encoding="utf-8")
        for name in ("gateway.conf", "conf.d/gateway_admin_session.conf")
    )
    login = (ROOT / "openresty" / "lua" / "admin_login.lua").read_text(encoding="utf-8")
    lab_access = (ROOT / "openresty" / "lua" / "lab_manager_access.lua").read_text(encoding="utf-8")
    assert "?token=" not in conf
    assert "content_by_lua_file /etc/openresty/lua/admin_login.lua" in conf
    assert "ngx.req.get_method() ~= \"POST\"" in login
    assert '"/lab-manager"' in login
    assert '"/ops"' in login
    assert '"/wallet-dashboard"' in login
    assert '"/billing"' in login
    assert "local max_age = 1800" in login
    assert "admin_session:" in login
    assert "resty.random" in login
    assert "admin_session:lab:" in lab_access
    assert "token, 1800" in lab_access
    assert "Max-Age=1800" in lab_access


def test_gateway_admin_web_does_not_persist_or_forward_tokens():
    web_files = list((ROOT / "web").rglob("*.js")) + list((ROOT / "web").rglob("*.html"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in web_files)
    assert "localStorage" not in content
    assert "tokenFromUrl" not in content
    assert "?token=" not in content
    assert "onclick=" not in content


def test_gateway_static_locations_send_strict_csp():
    openresty_root = ROOT / "openresty"
    conf = "\n".join(
        (openresty_root / name).read_text(encoding="utf-8")
        for name in (
            "gateway.conf",
            "conf.d/gateway_lab_manager.conf",
            "conf.d/gateway_wallet_dashboard.conf",
            "conf.d/gateway_institution_config.conf",
            "conf.d/gateway_admin_session.conf",
        )
    )
    assert conf.count("Content-Security-Policy") >= 3
    assert "script-src 'self'" in conf
    assert "style-src 'self'" in conf
    assert "script-src 'self' 'unsafe-inline'" not in conf
