from pathlib import Path

import worker


def test_guacamole_temp_user_cleanup_default_interval_is_900_seconds():
    assert worker.GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS == 900


def test_ops_worker_image_copies_the_dedicated_error_contract_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY errors.py /app/errors.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_pure_winrm_trust_helpers():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust.py /app/winrm_trust.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_store_helpers():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_store.py /app/winrm_trust_store.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_trust_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_trust_service.py /app/winrm_trust_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_session_policy():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_session_policy.py /app/winrm_session_policy.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_session_factory():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_session_factory.py /app/winrm_session_factory.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_execution_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_execution.py /app/winrm_command_execution.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_builders():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_builders.py /app/winrm_command_builders.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_winrm_command_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_command_service.py /app/winrm_command_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_values_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_values.py /app/heartbeat_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_service():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_service.py /app/heartbeat_service.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_heartbeat_stream():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY heartbeat_stream.py /app/heartbeat_stream.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_catalog_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_catalog.py /app/host_catalog.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_the_host_registry_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_registry.py /app/host_registry.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_inventory_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_inventory_values.py /app/host_inventory_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_discovery_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_discovery_values.py /app/host_discovery_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_host_provisioning_values():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY host_provisioning_values.py /app/host_provisioning_values.py" in dockerfile.read_text(encoding="utf-8")


def test_ops_worker_image_copies_winrm_credentials_resolution():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY winrm_credentials_resolution.py /app/winrm_credentials_resolution.py" in dockerfile.read_text(encoding="utf-8")


def test_main_starts_scheduler_and_serves_with_waitress(monkeypatch):
    calls = []

    monkeypatch.setenv("OPS_BIND", "127.0.0.1")
    monkeypatch.setenv("OPS_PORT", "9876")
    monkeypatch.setattr(worker, "start_scheduler", lambda: calls.append("scheduler"))
    monkeypatch.setattr(
        worker,
        "serve",
        lambda app, host, port: calls.append((app, host, port)),
    )

    worker.main()

    assert calls == ["scheduler", (worker.APP, "127.0.0.1", 9876)]
