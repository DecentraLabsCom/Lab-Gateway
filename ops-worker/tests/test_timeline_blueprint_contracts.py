from flask import Flask

import worker
from timeline_blueprint import create_timeline_blueprint


def test_timeline_blueprint_registers_read_route_and_forwards_query_values():
    app = Flask("timeline-blueprint-contract")
    calls = []
    payload = {"reservationId": "res-1", "operations": []}

    app.register_blueprint(
        create_timeline_blueprint(
            get_db_engine=lambda: calls.append("db") or object(),
            sanitize_limit=lambda value: calls.append(("limit", value)) or 2,
            sanitize_offset=lambda value: calls.append(("offset", value)) or 3,
            build_timeline=lambda reservation_id, limit, offset: calls.append(
                ("timeline", reservation_id, limit, offset)
            ) or payload,
            internal_error_response=lambda message, _exc: ({"error": message}, 500),
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/reservations/timeline"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "timeline.api_reservation_timeline"

    response = app.test_client().get(
        "/api/reservations/timeline?reservation_id=res-1&limit=9&offset=4"
    )

    assert response.status_code == 200
    assert response.get_json() == payload
    assert calls == ["db", ("limit", "9"), ("offset", "4"), ("timeline", "res-1", 2, 3)]


def test_worker_timeline_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/api/reservations/timeline"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "timeline.api_reservation_timeline"
