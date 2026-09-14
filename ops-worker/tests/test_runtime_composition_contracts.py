from runtime_composition import compose_worker_app


def test_compose_worker_app_preserves_context_facade_publish_and_registration_order():
    events = []
    providers = {"runtime": "live"}
    app = object()
    context = {"runtime": "live"}
    legacy = {"api_health": lambda: {"status": "ok"}}

    result_context, result_legacy = compose_worker_app(
        app,
        providers,
        context_factory=lambda values: events.append(("context", values)) or context,
        legacy_factory=lambda current: events.append(("legacy", current)) or legacy,
        register_blueprints=lambda current_app, current: events.append(
            ("blueprints", current_app, current, dict(providers))
        ),
    )

    assert result_context is context
    assert result_legacy is legacy
    assert providers["api_health"] is legacy["api_health"]
    assert [event[0] for event in events] == ["context", "legacy", "blueprints"]
    assert events[-1][3]["api_health"] is legacy["api_health"]
