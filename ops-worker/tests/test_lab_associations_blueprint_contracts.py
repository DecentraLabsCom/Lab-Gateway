from flask import Flask

from lab_associations_blueprint import create_lab_associations_blueprint


def test_lab_associations_blueprint_registers_and_serializes_calculated_associations():
    app = Flask("lab-associations-blueprint-contract")
    app.register_blueprint(
        create_lab_associations_blueprint(
            resolve_lab_associations=lambda: [
                {"labId": "lab-1", "hostName": "station-01"},
            ],
        )
    )

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/lab-associations"
    ]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}
    assert rules[0].endpoint == "lab_associations.api_lab_associations"

    response = app.test_client().get("/api/lab-associations")

    assert response.status_code == 200
    assert response.get_json() == {
        "associations": [
            {"labId": "lab-1", "hostName": "station-01"},
        ],
    }
