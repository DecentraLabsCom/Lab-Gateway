from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from database_context import DatabaseContext
from database_runtime import DatabaseRuntime, create_database_runtime


def test_database_runtime_forwards_engine_sql_and_logger_explicitly():
    calls = []
    sql_text = lambda statement: f"SQL:{statement}"
    logger = SimpleNamespace(warning="warn")
    context = DatabaseContext(
        database_is_usable=lambda engine, statement, **kwargs: calls.append(
            (engine, statement, kwargs)
        ) or True,
        get_sql_text=lambda: sql_text,
        get_logger=lambda: logger,
    )
    runtime = create_database_runtime(context)

    assert isinstance(runtime, DatabaseRuntime)
    assert runtime.database_is_usable("engine", "SELECT 1") is True
    assert calls == [
        (
            "engine",
            "SELECT 1",
            {"sql_text": sql_text, "logger": logger},
        )
    ]


def test_database_context_is_immutable():
    context = DatabaseContext(
        database_is_usable=lambda *args, **kwargs: True,
        get_sql_text=lambda: str,
        get_logger=lambda: SimpleNamespace(),
    )

    with pytest.raises(FrozenInstanceError):
        context.get_logger = lambda: SimpleNamespace()
