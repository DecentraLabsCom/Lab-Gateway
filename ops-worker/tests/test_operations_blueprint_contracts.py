from flask import Flask

import worker
from operations_blueprint import create_operations_blueprint


class _Rows:
    def all(self):
        return []


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def mappings(self):
        return _Rows()


class _Connection:
    def __init__(self):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, _statement, _params):
        self.calls += 1
        return _Result(0)


class _Engine:
    def begin(self):
        return _Connection()


def test_operations_blueprint_registers_read_route_and_uses_injected_dependencies():
    app = Flask("operations-blueprint-contract")
    calls = []

    app.register_blueprint(
        create_operations_blueprint(
            get_db_engine=lambda: calls.append("db") or _Engine(),
            find_host=lambda host_name: calls.append(("host", host_name)) or {"name": host_name},
            sanitize_limit=lambda value: int(value or 10),
            sanitize_offset=lambda value: int(value or 0),
            sql_text=lambda statement: statement,
            rows_to_operations=lambda rows: [],
            internal_error_response=lambda message, _exc: ({"error": message}, 500),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/operations/recent"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "operations.api_operations_recent"

    response = app.test_client().get("/api/operations/recent?host=lab-ws-01&limit=2&offset=3")

    assert response.status_code == 200
    assert response.get_json() == {
        "operations": [],
        "pagination": {
            "limit": 2,
            "offset": 3,
            "returned": 0,
            "total": 0,
            "nextOffset": 3,
            "hasMore": False,
            "page": 2,
            "pageSize": 2,
        },
    }
    assert calls == ["db", ("host", "lab-ws-01")]


def test_worker_operations_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/operations/recent"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "operations.api_operations_recent"
