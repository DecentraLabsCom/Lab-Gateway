from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_admin_bootstrap_is_post_only_and_cookies_are_path_scoped():
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
    login = (ROOT / "openresty" / "lua" / "admin_login.lua").read_text(encoding="utf-8")
    assert "?token=" not in conf
    assert "content_by_lua_file /etc/openresty/lua/admin_login.lua" in conf
    assert "ngx.req.get_method() ~= \"POST\"" in login
    assert '"/lab-manager"' in login
    assert '"/ops"' in login
    assert '"/wallet-dashboard"' in login
    assert '"/billing"' in login
    assert "local max_age = 900" in login
    assert "admin_session:" in login
    assert "resty.random" in login


def test_gateway_admin_web_does_not_persist_or_forward_tokens():
    web_files = list((ROOT / "web").rglob("*.js")) + list((ROOT / "web").rglob("*.html"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in web_files)
    assert "localStorage" not in content
    assert "tokenFromUrl" not in content
    assert "?token=" not in content
    assert "onclick=" not in content


def test_gateway_static_locations_send_strict_csp():
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
    assert conf.count("Content-Security-Policy") >= 3
    assert "script-src 'self'" in conf
    assert "style-src 'self'" in conf
    assert "script-src 'self' 'unsafe-inline'" not in conf
