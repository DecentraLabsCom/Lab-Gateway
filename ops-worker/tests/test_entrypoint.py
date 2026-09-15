from fnmatch import fnmatchcase
from pathlib import Path

import pytest

import worker


OPS_WORKER_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MODULES = tuple(sorted(path.name for path in OPS_WORKER_ROOT.glob("*.py")))


def test_guacamole_temp_user_cleanup_default_interval_is_900_seconds():
    assert worker.GUACAMOLE_TEMP_USER_CLEANUP_INTERVAL_SECONDS == 900


def test_ops_worker_image_groups_runtime_files_into_shallow_copy_layers():
    dockerfile = OPS_WORKER_ROOT / "Dockerfile"
    lines = [
        line.strip()
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("COPY ")
    ]

    assert lines == [
        "COPY requirements.txt .",
        "COPY *.py /app/",
        "COPY power /app/power",
    ]
    assert "legacy_api.py" not in dockerfile.read_text(encoding="utf-8")


@pytest.mark.parametrize("module_name", RUNTIME_MODULES)
def test_ops_worker_image_copies_each_runtime_module_through_the_python_glob(module_name):
    dockerfile = OPS_WORKER_ROOT / "Dockerfile"
    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    dockerignore = OPS_WORKER_ROOT / ".dockerignore"
    ignored_patterns = {
        line.strip().rstrip("/")
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert (OPS_WORKER_ROOT / module_name).is_file()
    assert "COPY *.py /app/" in dockerfile_text
    assert not any(fnmatchcase(module_name, pattern) for pattern in ignored_patterns)


def test_ops_worker_docker_context_excludes_development_and_host_configuration():
    dockerignore = OPS_WORKER_ROOT / ".dockerignore"
    ignored_paths = {
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        "tests/",
        "__pycache__/",
        ".pytest_cache/",
        ".pytest-tmp-revocation-spool/",
        ".coverage",
        ".coverage.*",
        "hosts.json",
    } <= ignored_paths


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
