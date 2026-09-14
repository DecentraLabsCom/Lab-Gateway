from types import SimpleNamespace

from database_runtime import DatabaseRuntime, create_database_runtime


def test_database_runtime_forwards_engine_sql_and_logger_dynamically():
    calls = []
    providers = {
        "_database_is_usable_impl": lambda engine, statement, **kwargs: calls.append(
            (engine, statement, kwargs)
        ) or True,
        "text": lambda statement: f"SQL:{statement}",
        "logging": SimpleNamespace(warning="warn"),
    }
    runtime = create_database_runtime(providers)

    assert isinstance(runtime, DatabaseRuntime)
    assert runtime.database_is_usable("engine", "SELECT 1") is True
    assert calls == [
        (
            "engine",
            "SELECT 1",
            {"sql_text": providers["text"], "logger": providers["logging"]},
        )
    ]
