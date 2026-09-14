from flask import Flask

import worker
from guacamole_connections_blueprint import create_guacamole_connections_blueprint


def test_guacamole_connections_blueprint_preserves_auth_and_projection_contract():
    app = Flask("guacamole-connections-blueprint-contract")
    connection = {"id": 7, "name": "RDP Lab", "hostname": "lab-01"}

    app.register_blueprint(
        create_guacamole_connections_blueprint(
            authorize=lambda: None,
            load_connections=lambda: ([connection], None),
            safe_connection_response=lambda value: {
                "id": value["id"],
                "name": value["name"],
            },
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/internal/guacamole/connections"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "guacamole_connections.api_internal_guacamole_connections"

    response = app.test_client().get("/internal/guacamole/connections")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "connections": [{"id": 7, "name": "RDP Lab"}],
    }


def test_worker_guacamole_connections_route_is_owned_by_the_blueprint_without_duplicates():
    rules = [
        rule for rule in worker.APP.url_map.iter_rules()
        if rule.rule == "/internal/guacamole/connections"
    ]

    assert len(rules) == 1
    assert rules[0].endpoint == "guacamole_connections.api_internal_guacamole_connections"
    assert callable(worker.api_internal_guacamole_connections)
