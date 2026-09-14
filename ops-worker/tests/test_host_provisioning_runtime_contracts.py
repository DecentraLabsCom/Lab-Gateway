from types import SimpleNamespace

from host_provisioning_runtime import HostProvisioningRuntime, create_host_provisioning_runtime


def test_host_provisioning_runtime_forwards_validation_and_payload_dependencies():
    calls = []
    providers = {
        "_sanitize_host_name_impl": lambda value, fallback, **kwargs: calls.append(
            ("name", value, fallback, kwargs)
        ) or ("station-01", None),
        "HOST_NAME_RE": "name-pattern",
        "_normalize_labs_impl": lambda value: calls.append(("labs", value)) or ["lab-1"],
        "_validate_labs_against_candidates_impl": lambda labs, candidates: calls.append(
            ("validate-labs", labs, candidates)
        ) or None,
        "_build_provisioned_host_impl": lambda payload, connection, **kwargs: calls.append(
            ("build", payload, connection, kwargs)
        ) or ({"name": "station-01"}, None),
        "sanitize_host_name": lambda value, fallback: ("station-01", None),
        "normalize_labs": lambda value: ["lab-1"],
        "validate_labs_against_candidates": lambda labs, candidates: None,
        "normalize_mac": lambda value: "AA:BB:CC:DD:EE:FF",
        "normalize_winrm_trust_ref": lambda value: "station-01",
    }
    runtime = create_host_provisioning_runtime(providers)

    assert isinstance(runtime, HostProvisioningRuntime)
    assert runtime.sanitize_host_name("station-01", "fallback") == ("station-01", None)
    assert runtime.normalize_labs("lab-1") == ["lab-1"]
    assert runtime.validate_labs_against_candidates(["lab-1"], ["lab-1"]) is None
    assert runtime.build_provisioned_host({"name": "station-01"}, {"hostname": "station-01"}) == (
        {"name": "station-01"},
        None,
    )
    assert any(call[0] == "build" for call in calls)


def test_host_provisioning_runtime_uses_mutable_normalization_callbacks():
    providers = {
        "_sanitize_host_name_impl": lambda value, fallback, **kwargs: (value or fallback, None),
        "HOST_NAME_RE": "name-pattern",
        "_normalize_labs_impl": lambda value: list(value or []),
        "_validate_labs_against_candidates_impl": lambda labs, candidates: None,
        "_build_provisioned_host_impl": lambda payload, connection, **kwargs: kwargs[
            "normalize_trust_ref_fn"
        ]("station"),
        "sanitize_host_name": lambda value, fallback: (value or fallback, None),
        "normalize_labs": lambda value: [],
        "validate_labs_against_candidates": lambda labs, candidates: None,
        "normalize_mac": lambda value: "first",
        "normalize_winrm_trust_ref": lambda value: "first",
    }
    runtime = create_host_provisioning_runtime(providers)

    assert runtime.build_provisioned_host({}, {}) == "first"
    providers["normalize_winrm_trust_ref"] = lambda value: "second"
    assert runtime.build_provisioned_host({}, {}) == "second"
