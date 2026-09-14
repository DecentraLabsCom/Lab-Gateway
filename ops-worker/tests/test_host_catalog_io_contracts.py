import json
import logging

from host_catalog_io import merge_host_configs, read_hosts_config


def test_read_hosts_config_contract_preserves_missing_and_normalization(tmp_path, caplog):
    missing = tmp_path / "missing.json"
    with caplog.at_level(logging.WARNING):
        assert read_hosts_config(str(missing), missing_ok=False) == {"hosts": []}
    assert "not found" in caplog.text

    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"hosts": "invalid"}), encoding="utf-8")
    assert read_hosts_config(str(invalid)) == {"hosts": []}

    scalar = tmp_path / "scalar.json"
    scalar.write_text("[]", encoding="utf-8")
    assert read_hosts_config(str(scalar)) == {"hosts": []}


def test_merge_host_configs_contract_preserves_case_insensitive_dynamic_precedence():
    result = merge_host_configs(
        {
            "hosts": [
                {"name": "Lab-01", "address": "10.0.0.1"},
                {"name": "static-only", "address": "10.0.0.2"},
            ]
        },
        {
            "hosts": [
                {"name": " lab-01 ", "address": "10.0.0.9"},
                {"name": "dynamic-only", "address": "10.0.0.3"},
                "ignored",
            ]
        },
    )

    assert result == {
        "hosts": [
            {"name": " lab-01 ", "address": "10.0.0.9"},
            {"name": "static-only", "address": "10.0.0.2"},
            {"name": "dynamic-only", "address": "10.0.0.3"},
        ]
    }
