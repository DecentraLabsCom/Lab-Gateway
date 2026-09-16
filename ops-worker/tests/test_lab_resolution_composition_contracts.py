from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Callable, cast

import lab_resolution_composition as composition


@dataclass(frozen=True)
class _Policy:
    lab_catalog_url: str = "http://blockchain-services:8080/lab-admin/labs"
    lab_catalog_token: str = "catalog-token"
    lab_catalog_token_header: str = "X-Lab-Manager-Token"
    lab_catalog_allow_insecure: bool = True
    lab_catalog_timeout_seconds: float = 4.0
    lab_catalog_cache_seconds: float = 15.0


def _policy() -> _Policy:
    return _Policy(
        lab_catalog_url="http://blockchain-services:8080/lab-admin/labs",
        lab_catalog_token="catalog-token",
        lab_catalog_token_header="X-Lab-Manager-Token",
        lab_catalog_allow_insecure=True,
        lab_catalog_timeout_seconds=4.0,
        lab_catalog_cache_seconds=15.0,
    )


def test_composition_binds_catalog_policy_and_live_dependency_ports(monkeypatch):
    captured = {}
    host_registry = object()
    guacamole_connections = object()
    parse_selector = lambda value: int(str(value).split(":id:", 1)[1])
    normalize_key = lambda value: str(value or "").strip().lower()
    http_get = cast(Callable[..., Any], object())
    logger = object()
    monotonic = cast(Callable[[], float], object())

    def capture_runtime(context):
        captured["context"] = context
        return "runtime"

    monkeypatch.setattr(composition, "create_lab_resolution_runtime", capture_runtime)

    runtime = composition.create_lab_resolution_composition(
        _policy(),
        get_host_registry=lambda: host_registry,
        get_guacamole_connections=lambda: guacamole_connections,
        get_parse_selector=lambda: parse_selector,
        get_normalize_key=lambda: normalize_key,
        get_http_get=lambda: http_get,
        get_logger=lambda: logger,
        get_monotonic=lambda: monotonic,
    )

    assert runtime == "runtime"
    context = captured["context"]
    assert context.get_catalog_url() == _policy().lab_catalog_url
    assert context.get_catalog_token() == _policy().lab_catalog_token
    assert context.get_catalog_token_header() == _policy().lab_catalog_token_header
    assert context.get_catalog_allow_insecure() is True
    assert context.get_catalog_timeout() == 4.0
    assert context.get_catalog_cache_seconds() == 15.0
    assert context.get_host_registry() is host_registry
    assert context.get_guacamole_connections() is guacamole_connections
    assert context.get_parse_selector() is parse_selector
    assert context.get_normalize_key() is normalize_key
    assert context.get_http_get() is http_get
    assert context.get_logger() is logger
    assert context.get_monotonic() is monotonic
    assert context.get_cache_lock() is context.get_cache_lock()


def test_worker_delegates_lab_resolution_composition():
    worker_source = Path("worker.py").read_text(encoding="utf-8")

    assert "create_lab_resolution_composition(" in worker_source
    assert "LabResolutionContext" not in worker_source
    assert "LAB_CATALOG_LOCK" not in worker_source
    assert "LAB_CATALOG_URL" not in worker_source
