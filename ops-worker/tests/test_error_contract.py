def test_internal_error_log_escapes_line_breaks(caplog):
    import logging

    import worker

    with worker.APP.test_request_context("/api/wol"), caplog.at_level(logging.ERROR):
        worker.internal_error_response("bad\r\nforged", RuntimeError("secret"))

    message = next(record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR)
    assert "bad\\r\\nforged" in message
    assert "bad\r\nforged" not in message
