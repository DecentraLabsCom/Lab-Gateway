from host_registry import HostRegistry


def test_host_registry_indexes_hosts_and_first_lab_mapping_case_insensitively():
    first = {"name": "Station-A", "address": "10.0.0.1", "labs": [42, "shared"]}
    second = {"name": "Station-B", "address": "10.0.0.2", "labs": ["shared", 43]}

    registry = HostRegistry({"hosts": [first, second]})

    assert registry.get("station-a") == first
    assert registry.get_by_lab("42") == first
    assert registry.get_by_lab("SHARED") == first
    assert registry.get_by_lab(43) == second
    assert registry.count() == 2


def test_host_registry_drops_inline_credentials_and_invalid_entries():
    registry = HostRegistry({
        "hosts": [
            {
                "name": "Station-A",
                "address": "10.0.0.1",
                "winrm_user": "user",
                "winrm_pass": "password",
            },
            {"name": "missing-address"},
        ]
    })

    assert registry.all_hosts() == [{"name": "Station-A", "address": "10.0.0.1"}]
