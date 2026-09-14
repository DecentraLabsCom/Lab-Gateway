import logging

from secret_values import env_or_secret_file


def test_env_or_secret_file_contract_prefers_nonempty_environment(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-value\n", encoding="utf-8")
    monkeypatch.setenv("OPS_TEST_SECRET", "env-value")
    monkeypatch.setenv("OPS_TEST_SECRET_FILE", str(secret_file))

    assert env_or_secret_file("OPS_TEST_SECRET", "fallback") == "env-value"


def test_env_or_secret_file_contract_reads_and_strips_secret_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("  file-value  \n", encoding="utf-8")
    monkeypatch.delenv("OPS_TEST_SECRET", raising=False)
    monkeypatch.setenv("OPS_TEST_SECRET_FILE", str(secret_file))

    assert env_or_secret_file("OPS_TEST_SECRET", "fallback") == "file-value"


def test_env_or_secret_file_contract_returns_default_for_missing_or_unreadable_file(
    monkeypatch,
    caplog,
):
    monkeypatch.delenv("OPS_TEST_SECRET", raising=False)
    monkeypatch.setenv("OPS_TEST_SECRET_FILE", "C:\\missing\\secret")

    with caplog.at_level(logging.WARNING):
        assert env_or_secret_file("OPS_TEST_SECRET", "fallback") == "fallback"

    assert "Unable to read secret file for OPS_TEST_SECRET" in caplog.text
