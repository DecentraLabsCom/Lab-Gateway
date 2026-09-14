import worker

from host_config_service import resolve_host_secret_refs


def test_resolve_host_secret_refs_contract_sets_reference_and_removes_legacy_secrets():
    warnings = []
    raw = {
        "hosts": [
            {
                "name": "station-01",
                "address": "192.168.1.50",
                "winrm_user": "legacy-user",
                "winrm_pass": "legacy-pass",
            },
            {
                "name": "station-02",
                "address": "192.168.1.51",
                "credential_ref": "Managed-02",
            },
        ]
    }

    result = resolve_host_secret_refs(
        raw,
        credential_ref_for_host=lambda host: str(
            host.get("credential_ref") or host.get("address") or host.get("name")
        ).lower(),
        credentials_configured=lambda ref: ref == "managed-02",
        warn=lambda *args: warnings.append(args),
    )

    assert result is raw
    assert raw["hosts"] == [
        {"name": "station-01", "address": "192.168.1.50", "credential_ref": "192.168.1.50"},
        {"name": "station-02", "address": "192.168.1.51", "credential_ref": "Managed-02"},
    ]
    assert warnings == [("Missing WinRM credentials for host %s", "station-01")]


def test_load_config_contract_preserves_read_merge_validate_and_secret_resolution(
    monkeypatch,
):
    calls = []
    base = {"hosts": [{"name": "base"}]}
    dynamic = {"hosts": [{"name": "dynamic"}]}
    merged = {"hosts": [{"name": "merged"}]}
    resolved = {"hosts": [{"name": "resolved"}]}

    monkeypatch.setattr(worker, "CONFIG_PATH", "base-hosts.json")
    monkeypatch.setattr(worker, "DYNAMIC_CONFIG_PATH", "dynamic-hosts.json")

    def read_config(path, missing_ok=True):
        calls.append(("read", path, missing_ok))
        return base if path == "base-hosts.json" else dynamic

    def merge_configs(received_base, received_dynamic):
        calls.append(("merge", received_base, received_dynamic))
        return merged

    def validate(config):
        calls.append(("validate", config))

    def resolve_secrets(config):
        calls.append(("resolve", config))
        return resolved

    monkeypatch.setattr(worker, "read_hosts_config", read_config)
    monkeypatch.setattr(worker, "merge_host_configs", merge_configs)
    monkeypatch.setattr(worker, "validate_winrm_catalog", validate)
    monkeypatch.setattr(worker, "resolve_host_secret_refs", resolve_secrets)

    assert worker.load_config() is resolved
    assert calls == [
        ("read", "base-hosts.json", False),
        ("read", "dynamic-hosts.json", True),
        ("merge", base, dynamic),
        ("validate", merged),
        ("resolve", merged),
    ]


def test_load_dynamic_config_contract_reads_optional_dynamic_path(monkeypatch):
    calls = []
    dynamic = {"hosts": [{"name": "dynamic"}]}

    monkeypatch.setattr(worker, "DYNAMIC_CONFIG_PATH", "dynamic-hosts.json")

    def read_config(path, missing_ok=True):
        calls.append((path, missing_ok))
        return dynamic

    monkeypatch.setattr(worker, "read_hosts_config", read_config)

    assert worker.load_dynamic_config() is dynamic
    assert calls == [("dynamic-hosts.json", True)]


def test_write_dynamic_config_contract_writes_indented_json_and_replaces_atomically(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "nested" / "hosts.json"
    config = {"hosts": [{"name": "dynamic", "labs": ["1"]}]}
    replacements = []
    original_replace = worker.os.replace

    def replace_file(source, destination):
        replacements.append((source, destination))
        return original_replace(source, destination)

    monkeypatch.setattr(worker, "DYNAMIC_CONFIG_PATH", str(target))
    monkeypatch.setattr(worker.os, "replace", replace_file)

    worker.write_dynamic_config(config)

    assert target.read_text(encoding="utf-8") == '{\n  "hosts": [\n    {\n      "name": "dynamic",\n      "labs": [\n        "1"\n      ]\n    }\n  ]\n}\n'
    assert replacements == [(f"{target}.tmp", str(target))]
    assert not (tmp_path / "nested" / "hosts.json.tmp").exists()


def test_write_dynamic_config_contract_propagates_replace_failure(monkeypatch, tmp_path):
    target = tmp_path / "hosts.json"
    failure = PermissionError("catalog is read-only")

    monkeypatch.setattr(worker, "DYNAMIC_CONFIG_PATH", str(target))
    monkeypatch.setattr(
        worker.os,
        "replace",
        lambda _source, _destination: (_ for _ in ()).throw(failure),
    )

    try:
        worker.write_dynamic_config({"hosts": []})
    except PermissionError as exc:
        assert exc is failure
    else:
        raise AssertionError("write_dynamic_config must propagate replace failures")


def test_upsert_dynamic_host_contract_replaces_case_insensitive_name(monkeypatch):
    calls = []
    config = {
        "hosts": [
            {"name": "Keep", "address": "10.0.0.1"},
            {"name": "Lab-01", "address": "old"},
            "invalid-entry",
        ],
        "version": 2,
    }
    replacement = {"name": "lab-01", "address": "new"}

    monkeypatch.setattr(worker, "load_dynamic_config", lambda: calls.append("load") or config)
    monkeypatch.setattr(worker, "write_dynamic_config", lambda received: calls.append(("write", received)))

    assert worker.upsert_dynamic_host(replacement) is None
    assert config == {
        "hosts": [
            {"name": "Keep", "address": "10.0.0.1"},
            replacement,
        ],
        "version": 2,
    }
    assert calls == ["load", ("write", config)]


def test_upsert_dynamic_host_contract_appends_when_name_is_new(monkeypatch):
    calls = []
    config = {"hosts": [{"name": "existing"}]}
    new_host = {"name": "new"}

    monkeypatch.setattr(worker, "load_dynamic_config", lambda: config)
    monkeypatch.setattr(worker, "write_dynamic_config", lambda received: calls.append(received))

    worker.upsert_dynamic_host(new_host)

    assert config["hosts"] == [{"name": "existing"}, new_host]
    assert calls == [config]


def test_upsert_dynamic_host_contract_propagates_write_failure(monkeypatch):
    failure = PermissionError("catalog is read-only")
    monkeypatch.setattr(worker, "load_dynamic_config", lambda: {"hosts": []})
    monkeypatch.setattr(
        worker,
        "write_dynamic_config",
        lambda _config: (_ for _ in ()).throw(failure),
    )

    try:
        worker.upsert_dynamic_host({"name": "new"})
    except PermissionError as exc:
        assert exc is failure
    else:
        raise AssertionError("upsert_dynamic_host must propagate write failures")
