from flask import jsonify

import app_factory
import worker


def test_app_factory_preserves_import_name_and_registers_cross_cutting_hooks():
    app = app_factory.create_app(
        "contract.import",
        internal_error_response=lambda context, exc: (
            jsonify({"context": context, "error": type(exc).__name__}),
            599,
        ),
        internal_auth_token=lambda: "token",
        internal_auth_header=lambda: "X-Contract-Token",
        requires_internal_auth=lambda path: path.startswith("/api/"),
    )

    assert app.import_name == "contract.import"
    assert Exception in app.error_handler_spec[None][None]
    assert len(app.before_request_funcs[None]) == 1


def test_worker_constructs_app_through_the_factory_and_keeps_legacy_app_surface():
    source = open(worker.__file__, encoding="utf-8").read()

    assert "APP = create_app(" in source
    assert "APP = Flask(__name__)" not in source
    assert worker.APP.import_name == "worker"


def test_worker_delegates_all_blueprint_registration_to_the_app_factory():
    source = open(worker.__file__, encoding="utf-8").read()

    assert "APP.register_blueprint(" not in source
    assert "compose_worker_app(" in source
    assert "register_blueprints=register_blueprints" in source
