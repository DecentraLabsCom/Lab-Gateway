import worker


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self.rows)


class _Connection:
    def __init__(self, connection_rows, user_rows=None, user_error=None, calls=None):
        self.connection_rows = connection_rows
        self.user_rows = user_rows or []
        self.user_error = user_error
        self.calls = calls if calls is not None else []

    def execute(self, statement):
        sql = str(statement)
        self.calls.append(sql)
        if "FROM guacamole_connection c" in sql:
            return _Result(self.connection_rows)
        if self.user_error:
            raise self.user_error
        return _Result(self.user_rows)


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, _exc_type, _exc, _traceback):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _Transaction(self.connection)


class _Logger:
    def __init__(self):
        self.calls = []

    def warning(self, *args):
        self.calls.append(args)


def test_load_guacamole_connections_contract_handles_unconfigured_engine(monkeypatch):
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", None)

    assert worker.load_guacamole_connections() == ([], "Guacamole database not configured")


def test_load_guacamole_connections_contract_projects_connections_and_users(monkeypatch):
    calls = []
    connection = _Connection(
        [
            {
                "connection_id": 7,
                "connection_name": "RDP Lab",
                "protocol": "rdp",
                "hostname": "lab-01",
                "port": "3389",
            },
            {
                "connection_id": 8,
                "connection_name": "SSH Lab",
                "protocol": "ssh",
                "hostname": "lab-02",
                "port": "22",
            },
        ],
        [
            {"connection_id": 7, "username": "alice"},
            {"connection_id": 7, "username": "bob"},
        ],
        calls=calls,
    )
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", _Engine(connection))

    result, error = worker.load_guacamole_connections()

    assert error is None
    assert result == [
        {
            "id": 7,
            "selector": "guac:id:7",
            "name": "RDP Lab",
            "protocol": "rdp",
            "hostname": "lab-01",
            "port": "3389",
            "users": ["alice", "bob"],
        },
        {
            "id": 8,
            "selector": "guac:id:8",
            "name": "SSH Lab",
            "protocol": "ssh",
            "hostname": "lab-02",
            "port": "22",
            "users": [],
        },
    ]
    assert len(calls) == 2
    assert "ORDER BY c.connection_id ASC" in calls[0]
    assert "e.name NOT LIKE 'dlabs-res-%'" in calls[1]


def test_load_guacamole_connections_contract_ignores_user_query_failure(monkeypatch):
    failure = RuntimeError("users query failed")
    logger = _Logger()
    connection = _Connection(
        [{"connection_id": 7, "connection_name": "RDP Lab", "protocol": "rdp", "hostname": "lab-01", "port": "3389"}],
        user_error=failure,
    )
    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", _Engine(connection))
    monkeypatch.setattr(worker, "logging", logger)

    result, error = worker.load_guacamole_connections()

    assert error is None
    assert result[0]["users"] == []
    assert logger.calls == [("Unable to load Guacamole connection users: %s", failure)]


def test_load_guacamole_connections_contract_closes_on_connection_query_failure(monkeypatch):
    failure = RuntimeError("connections query failed")
    logger = _Logger()

    class FailingConnection:
        def execute(self, _statement):
            raise failure

    monkeypatch.setattr(worker, "GUACAMOLE_DB_ENGINE", _Engine(FailingConnection()))
    monkeypatch.setattr(worker, "logging", logger)

    assert worker.load_guacamole_connections() == ([], "Guacamole connection inventory unavailable")
    assert logger.calls == [("Unable to load Guacamole connections: %s", failure)]
