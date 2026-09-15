from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_public_health_is_aggregate_only_and_details_are_guarded():
    conf = (ROOT / "openresty" / "gateway.conf").read_text(encoding="utf-8")
    ops_include = (ROOT / "openresty" / "conf.d" / "gateway_ops.conf").read_text(encoding="utf-8")
    effective_conf = conf + "\n" + ops_include
    public_health = (ROOT / "openresty" / "lua" / "public_health.lua").read_text(encoding="utf-8")
    details_guard = (ROOT / "openresty" / "lua" / "health_details_access.lua").read_text(encoding="utf-8")

    assert "location = /health" in effective_conf
    assert "location = /ops/health" in effective_conf
    assert "location = /gateway/health" in effective_conf
    assert effective_conf.count("content_by_lua_file /etc/openresty/lua/public_health.lua;") == 3
    assert "location = /health/details" in effective_conf
    assert "location = /ops/health/details" in effective_conf
    assert "location = /gateway/health/details" in effective_conf
    assert "health_details_access.lua" in effective_conf
    assert "public = true" in public_health
    assert "remote_public_key" not in public_health
    assert "private_key" not in public_health
    assert 'loadfile("/etc/openresty/lua/lab_manager_access.lua")' in details_guard
    assert "return guard()" in details_guard


def test_ops_worker_container_and_winrm_policy_are_hardened():
    dockerfile = (ROOT / "ops-worker" / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    worker = (ROOT / "ops-worker" / "worker.py").read_text(encoding="utf-8")
    runtime_values = (ROOT / "ops-worker" / "runtime_values.py").read_text(encoding="utf-8")
    winrm_policy = (ROOT / "ops-worker" / "winrm_session_policy.py").read_text(encoding="utf-8")
    sample = (ROOT / "ops-worker" / "hosts.sample.json").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "useradd" in dockerfile and "USER opsworker" in dockerfile
    assert "OPS_UID: ${HOST_UID:-1000}" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
    assert "WINRM_PORT = 5986" in runtime_values
    assert "WinRM HTTPS is required by gateway policy" in winrm_policy
    assert "request port does not match the host WinRM policy" in winrm_policy
    assert "request transport does not match the host WinRM policy" in winrm_policy
    assert '"winrm_use_ssl": true' in sample
    assert '"winrm_port": 5986' in sample
    assert "WINRM_MANAGEMENT_CIDRS=" in env


def test_noncryptographic_jwt_module_is_absent():
    assert not (ROOT / "openresty" / "lua" / "jwt_handler.lua").exists()
    assert not (ROOT / "openresty" / "lua" / "modules" / "jwt_handler.lua").exists()
    run_lua = (ROOT / "openresty" / "tests" / "run.lua").read_text(encoding="utf-8")
    assert "jwt_handler_spec" not in run_lua
