from unittest.mock import Mock

import pytest

from guacamole_provision_service import (
    cleanup_expired_temporary_users,
    delete_temporary_user,
    provision_temporary_user,
)


class _Dialect:
    def __init__(self, name="sqlite"):
        self.name = name


class _Result:
    def __init__(self, scalar_value=None, rowcount=0):
        self.scalar_value = scalar_value
        self.rowcount = rowcount

    def scalar(self):
        return self.scalar_value


class _Connection:
    def __init__(self, dialect_name="sqlite", entity_id=7, cleanup_count=0):
        self.dialect = _Dialect(dialect_name)
        self.entity_id = entity_id
        self.cleanup_count = cleanup_count
        self.calls = []

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        if "SELECT entity_id" in statement:
            return _Result(self.entity_id)
        if statement.lstrip().upper().startswith("DELETE") and "guacamole_entity" in statement:
            return _Result(rowcount=self.cleanup_count)
        return _Result()


class _Begin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _Begin(self.connection)


def _common(connection, *, resolve=None):
    return {
        "engine": _Engine(connection),
        "parse_selector": lambda _selector: 42,
        "resolve_connection": resolve or (lambda _connection_id: {"id": 42, "name": "RDP Lab"}),
        "safe_connection_response": lambda value: {"selector": "guac:id:42", "name": value["name"]},
        "sql_text": lambda value: value,
        "date_from_epoch": lambda _value: "2026-12-01",
        "logger": Mock(),
    }


def test_provision_temporary_user_preserves_sql_permission_and_response_contract():
    connection = _Connection()
    result = provision_temporary_user(
        "guac:id:42",
        "session-1",
        1800000000,
        True,
        **_common(connection),
    )

    assert result == {
        "success": True,
        "sessionId": "session-1",
        "username": "dlabs-res-session-1",
        "connection": {"selector": "guac:id:42", "name": "RDP Lab"},
    }
    statements = [call[0] for call in connection.calls]
    assert "INSERT OR IGNORE INTO guacamole_entity" in statements[0]
    assert "INSERT OR REPLACE INTO guacamole_user" in statements[2]
    assert "INSERT OR REPLACE INTO guacamole_connection_permission" in statements[3]


def test_provision_temporary_user_rejects_invalid_session_and_missing_connection():
    connection = _Connection()
    with pytest.raises(ValueError, match="sessionId is required"):
        provision_temporary_user(
            "guac:id:42",
            "bad/session",
            None,
            True,
            **_common(connection),
        )

    with pytest.raises(ValueError, match="connection 42 not found"):
        provision_temporary_user(
            "guac:id:42",
            "session-2",
            None,
            True,
            **_common(connection, resolve=lambda _id: None),
        )


def test_delete_temporary_user_is_idempotent_and_cleanup_returns_deleted_count():
    missing = _Connection(entity_id=None)
    common = _common(missing)
    assert delete_temporary_user(
        "session-1",
        engine=common["engine"],
        sql_text=common["sql_text"],
        logger=common["logger"],
    ) is False

    cleanup_connection = _Connection(cleanup_count=3)
    common = _common(cleanup_connection)
    assert cleanup_expired_temporary_users(
        engine=common["engine"],
        sql_text=common["sql_text"],
        logger=common["logger"],
    ) == 3

    assert cleanup_expired_temporary_users(
        engine=None,
        sql_text=common["sql_text"],
        logger=common["logger"],
    ) == 0
