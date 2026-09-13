from config import load_config


def test_load_config_preserves_production_defaults_and_derived_audit_url():
    config = load_config({})

    assert config.fmu_data_path == "/app/fmu-data"
    assert config.max_simulation_timeout == 300
    assert config.max_concurrent_per_model == 10
    assert config.fmu_backend_mode == "station"
    assert config.fmu_local_dev_mode is False
    assert config.fmu_local_realtime_enabled is False
    assert config.access_audit_url == (
        "http://blockchain-services:8080/access-audit/internal/session-observed"
    )


def test_load_config_normalizes_flags_and_reads_secret_file(tmp_path):
    token_file = tmp_path / "ws-token"
    token_file.write_text("  internal-token\n", encoding="utf-8")

    config = load_config({
        "FMU_INTERNAL_WS_TOKEN_FILE": str(token_file),
        "FMU_LOCAL_DEV_MODE": "YES",
        "FMU_LOCAL_REALTIME_ENABLED": "on",
        "FMU_BACKEND_MODE": " LOCAL ",
        "AUTH_SESSION_TICKET_REDEEM_URL": "https://auth.example/redeem",
        "ACCESS_AUDIT_URL": "  https://audit.example/observed  ",
        "FMU_SESSION_OBSERVATION_MAX_ATTEMPTS": "0",
    })

    assert config.internal_ws_token == "internal-token"
    assert config.fmu_backend_mode == "local"
    assert config.fmu_local_dev_mode is True
    assert config.fmu_local_realtime_enabled is True
    assert config.access_audit_url == "https://audit.example/observed"
    assert config.fmu_session_observation_max_attempts == 1
