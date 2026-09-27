from lab_status_wake import fetch_latest_wake_operations


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return Result(self.rows)


def test_fetch_latest_wake_operations_returns_one_newest_row_per_lab_without_secrets():
    connection = Connection([
        {"lab_id": "7", "status": "completed", "success": True, "created_at": "new"},
        {"lab_id": "7", "status": "failed", "success": False, "created_at": "old"},
        {"lab_id": "8", "status": "failed", "success": False, "created_at": "new"},
    ])

    result = fetch_latest_wake_operations(
        connection,
        ["7", "7", "8"],
        sql_text=lambda value: value,
    )

    assert result == {
        "7": {"status": "completed", "success": True, "created_at": "new"},
        "8": {"status": "failed", "success": False, "created_at": "new"},
    }
    assert "payload" not in connection.statement
    assert connection.params == {"wake_action": "wake", "lab_id_0": "7", "lab_id_1": "8"}
