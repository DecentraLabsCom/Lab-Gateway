import worker


EXPECTED_ROUTE_METHODS = {
    "/aas-admin/lab/<lab_id>/sync": {"POST"},
    "/api/aas-sync": {"POST"},
    "/api/demo/end": {"POST"},
    "/api/demo/event": {"POST"},
    "/api/demo/start": {"POST"},
    "/api/heartbeat/poll": {"POST"},
    "/api/heartbeat/stream": {"GET"},
    "/api/hosts": {"GET"},
    "/api/hosts/<host_name>": {"PATCH"},
    "/api/hosts/<host_name>/winrm-trust": {"DELETE", "GET", "PUT"},
    "/api/hosts/<host_name>/winrm-trust/preview": {"POST"},
    "/api/hosts/discover": {"POST"},
    "/api/hosts/local-mode": {"POST"},
    "/api/hosts/provision": {"POST"},
    "/api/hosts/reload": {"POST"},
    "/api/hosts/winrm-credentials": {"POST"},
    "/api/labs/<lab_id>/power/end": {"POST"},
    "/api/labs/<lab_id>/power/start": {"POST"},
    "/api/operations/recent": {"GET"},
    "/api/power/controllers": {"GET", "POST"},
    "/api/power/controllers/<controller_id>": {"PUT"},
    "/api/power/controllers/<controller_id>/outlets/<outlet_id>/commands": {"POST"},
    "/api/power/controllers/status": {"GET"},
    "/api/power/credentials": {"GET", "POST"},
    "/api/power/mock/reset": {"POST"},
    "/api/power/operations": {"GET"},
    "/api/power/policies": {"GET"},
    "/api/power/policies/<lab_id>": {"PUT"},
    "/api/reservations/end": {"POST"},
    "/api/reservations/start": {"POST"},
    "/api/reservations/timeline": {"GET"},
    "/api/winrm": {"POST"},
    "/api/wol": {"POST"},
    "/health": {"GET"},
    "/internal/guacamole-token-revocations": {"POST"},
    "/internal/guacamole/connections": {"GET"},
    "/internal/guacamole/provision": {"POST"},
    "/internal/guacamole/provision/<session_id>": {"DELETE"},
    "/internal/session-observations": {"POST"},
    "/static/<path:filename>": {"GET"},
}


def test_route_inventory_contract_freezes_paths_and_methods():
    route_methods = {}
    for rule in worker.APP.url_map.iter_rules():
        methods = frozenset(rule.methods - {"HEAD", "OPTIONS"})
        route_methods.setdefault(rule.rule, set()).update(methods)

    assert route_methods == EXPECTED_ROUTE_METHODS
