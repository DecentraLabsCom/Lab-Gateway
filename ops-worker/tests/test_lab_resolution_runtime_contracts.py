from lab_resolution_context import LabResolutionContext
from lab_resolution_runtime import LabResolutionRuntime


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_runtime_fetches_catalog_once_within_cache_window_and_resolves_both_directions():
    calls = []
    clock = [100.0]
    hosts = [{"name": "station-01", "address": "192.168.1.51"}]
    connections = [{"id": 5, "hostname": "station-01"}]
    context = LabResolutionContext(
        get_catalog_url=lambda: "https://blockchain.example/lab-admin/labs",
        get_catalog_token=lambda: "token",
        get_catalog_token_header=lambda: "X-Lab-Manager-Token",
        get_catalog_allow_insecure=lambda: False,
        get_catalog_timeout=lambda: 3,
        get_catalog_cache_seconds=lambda: 15,
        get_http_get=lambda: lambda *_args, **_kwargs: calls.append("fetch") or type(
            "Response", (), {"status_code": 200, "json": lambda _self: {"labs": [
                {"labId": "lab-1", "accessKey": "guac:id:5"},
            ]}}
        )(),
        get_logger=lambda: type("Logger", (), {"warning": lambda *_args, **_kwargs: None})(),
        get_cache_lock=lambda: _Lock(),
        get_host_registry=lambda: type("Registry", (), {"all_hosts": lambda _self: hosts})(),
        get_guacamole_connections=lambda: (connections, None),
        get_parse_selector=lambda: lambda value: int(str(value).split(":id:", 1)[1]),
        get_normalize_key=lambda: lambda value: str(value or "").strip().lower(),
        get_monotonic=lambda: lambda: clock[0],
    )
    runtime = LabResolutionRuntime(context)

    assert runtime.resolve_lab_access_key("lab-1") == "guac:id:5"
    assert runtime.resolve_host_by_lab("lab-1") == hosts[0]
    assert runtime.resolve_lab_ids_for_host(hosts[0]) == ["lab-1"]
    assert runtime.resolve_lab_associations() == [
        {"labId": "lab-1", "hostName": "station-01"},
    ]
    assert calls == ["fetch"]
