from runtime_composition import compose_worker_app


def test_compose_worker_app_builds_context_then_registers_blueprints():
    events = []
    providers = {"runtime": "live"}
    app = object()
    context = {"runtime": "live"}

    result = compose_worker_app(
        app,
        providers,
        context_factory=lambda values: events.append(("context", values)) or context,
        register_blueprints=lambda current_app, current: events.append(
            ("blueprints", current_app, current, dict(providers))
        ),
    )

    assert result is context
    assert [event[0] for event in events] == ["context", "blueprints"]
    assert events[-1][3] == {"runtime": "live"}
