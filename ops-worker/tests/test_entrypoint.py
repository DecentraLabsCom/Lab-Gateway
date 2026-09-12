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
