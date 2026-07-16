from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_health_is_aggregate_only_and_details_are_guarded():
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")
    public_health = (ROOT / "openresty" / "lua" / "public_health.lua").read_text(encoding="utf-8")
    details_guard = (ROOT / "openresty" / "lua" / "health_details_access.lua").read_text(encoding="utf-8")

    assert "location = /health" in conf
    assert "location = /ops/health" in conf
    assert "location = /gateway/health" in conf
    assert conf.count("content_by_lua_file /etc/openresty/lua/public_health.lua;") == 3
    assert "location = /health/details" in conf
    assert "location = /ops/health/details" in conf
    assert "location = /gateway/health/details" in conf
    assert "health_details_access.lua" in conf
    assert "public = true" in public_health
    assert "remote_public_key" not in public_health
    assert "private_key" not in public_health
    assert "dofile(\"/etc/openresty/lua/lab_manager_access.lua\")" in details_guard


def test_ops_worker_container_and_winrm_policy_are_hardened():
    dockerfile = (ROOT / "ops-worker" / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    worker = (ROOT / "ops-worker" / "worker.py").read_text(encoding="utf-8")
    sample = (ROOT / "ops-worker" / "hosts.sample.json").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "useradd" in dockerfile and "USER opsworker" in dockerfile
    assert "OPS_UID: ${HOST_UID:-1000}" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
    assert "WINRM_REQUIRE_SSL" in worker
    assert "WinRM HTTPS is required by gateway policy" in worker
    assert "request port does not match the host WinRM policy" in worker
    assert "request transport does not match the host WinRM policy" in worker
    assert '"winrm_use_ssl": true' in sample
    assert '"winrm_port": 5986' in sample
    assert "WINRM_REQUIRE_SSL=true" in env


def test_legacy_noncryptographic_jwt_module_is_removed():
    assert not (ROOT / "openresty" / "lua" / "jwt_handler.lua").exists()
    assert not (ROOT / "openresty" / "lua" / "modules" / "jwt_handler.lua").exists()
    run_lua = (ROOT / "openresty" / "tests" / "run.lua").read_text(encoding="utf-8")
    readme = (ROOT / "openresty" / "tests" / "README.md").read_text(encoding="utf-8")
    assert "jwt_handler_spec" not in run_lua
    assert "compatibility module was removed" in readme
