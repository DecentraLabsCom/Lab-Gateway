from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_gateway_error_contract_does_not_return_exception_text():
    ops = (ROOT / "ops-worker" / "worker.py").read_text(encoding="utf-8")
    aas = (ROOT / "ops-worker" / "aas_generator.py").read_text(encoding="utf-8")
    auth = (ROOT / "fmu-runner" / "auth.py").read_text(encoding="utf-8")
    backend = (ROOT / "fmu-runner" / "fmu_backend.py").read_text(encoding="utf-8")
    main = (ROOT / "fmu-runner" / "main.py").read_text(encoding="utf-8")
    realtime = (ROOT / "fmu-runner" / "realtime_ws.py").read_text(encoding="utf-8")
    station = (ROOT / "fmu-runner" / "station_ws_proxy.py").read_text(encoding="utf-8")

    assert "def internal_error_response" in ops
    assert "def handle_unexpected_exception" in ops
    assert 'jsonify({"error": str(exc)}), 500' not in ops
    assert 'jsonify({"success": False, "error": str(exc)}), 500' not in ops
    assert 'result["error"] = f"BaSyx unreachable: {exc}"' not in aas
    assert 'detail=f"Invalid token: {exc}"' not in auth
    assert 'detail=f"Station backend unavailable: {exc}"' not in backend
    assert 'detail=f"Simulation error: {exc}"' not in main
    assert 'message=str(exc)' not in realtime
    assert 'message=str(exc.detail)' not in station
    assert 'message=str(detail)' not in station


def test_guacamole_proxy_normalizes_connection_upgrade_header():
    nginx = (ROOT / "openresty" / "nginx.conf").read_text(encoding="utf-8")
    conf = (ROOT / "openresty" / "lab_access.conf").read_text(encoding="utf-8")

    assert "map $http_upgrade $connection_upgrade" in nginx
    assert "default upgrade;" in nginx
    assert "close;" in nginx
    assert "proxy_set_header Connection $connection_upgrade;" in conf
    assert "proxy_set_header Connection $http_connection;" not in conf
