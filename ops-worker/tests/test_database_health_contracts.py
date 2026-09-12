import worker


class _Result:
    def first(self):
        return (1,)


class _Connection:
    def __init__(self, calls, failure=None):
        self.calls = calls
        self.failure = failure

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def execute(self, statement):
        if self.failure:
            raise self.failure
        self.calls.append(str(statement))
        return _Result()


class _Engine:
    def __init__(self, calls, failure=None):
        self.calls = calls
        self.failure = failure

    def connect(self):
        return _Connection(self.calls, self.failure)


class _Logger:
    def __init__(self):
        self.calls = []

    def warning(self, *args):
        self.calls.append(args)


def test_database_is_usable_contract_returns_false_without_engine():
    assert worker.database_is_usable(None, "SELECT 1") is False


def test_database_is_usable_contract_executes_statement_and_returns_true(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "DB_ENGINE", _Engine(calls))

    assert worker.database_is_usable(worker.DB_ENGINE, "SELECT 1") is True
    assert calls == ["SELECT 1"]


def test_database_is_usable_contract_logs_and_returns_false_on_failure(monkeypatch):
    failure = RuntimeError("database unavailable")
    logger = _Logger()
    monkeypatch.setattr(worker, "logging", logger)

    assert worker.database_is_usable(_Engine([], failure), "SELECT 1") is False
    assert logger.calls == [("Health database check failed: %s", failure)]
