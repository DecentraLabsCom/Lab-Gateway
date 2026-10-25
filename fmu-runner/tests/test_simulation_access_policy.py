import pytest

from simulation_access_policy import (
    AccessDenied,
    build_effective_policy,
    build_part4_access_rules,
    compile_part4_access_rules,
    filter_fmi_values,
    filter_model_description,
    fmi_interface_digest,
    validate_reads,
    validate_writes,
)


@pytest.fixture
def metadata():
    return {
        "fmiVersion": "3.0",
        "modelVariables": [
            {"name": "command", "causality": "input", "variability": "continuous"},
            {"name": "mode", "causality": "input", "variability": "constant"},
            {"name": "gain", "causality": "parameter", "variability": "fixed"},
            {"name": "calibration", "causality": "parameter", "variability": "constant"},
            {"name": "speed", "causality": "output", "variability": "continuous"},
            {"name": "computed", "causality": "calculatedParameter", "variability": "fixed"},
            {"name": "clock", "causality": "independent", "variability": "continuous"},
            {"name": "internal", "causality": "local", "variability": "continuous"},
            {"name": "dimensions", "causality": "structuralParameter", "variability": "fixed"},
        ],
    }


def test_fmi_defaults_follow_causality_variability_and_runtime_support(metadata):
    policy = build_effective_policy(metadata)

    assert policy["variables"]["command"] == {
        "read": True,
        "writeAt": ["initialization", "runtime"],
    }
    assert policy["variables"]["mode"] == {
        "read": True,
        "writeAt": ["initialization"],
    }
    assert policy["variables"]["gain"] == {
        "read": True,
        "writeAt": ["initialization"],
    }
    assert policy["variables"]["calibration"] == {"read": True, "writeAt": []}
    assert policy["variables"]["speed"] == {"read": True, "writeAt": []}
    assert policy["variables"]["computed"] == {"read": True, "writeAt": []}
    assert policy["variables"]["clock"] == {"read": True, "writeAt": []}
    assert policy["variables"]["internal"] == {"read": False, "writeAt": []}
    assert policy["variables"]["dimensions"] == {"read": True, "writeAt": []}


def test_unknown_fmi_causality_or_variability_does_not_grant_writes_or_reads():
    policy = build_effective_policy({
        "modelVariables": [
            {"name": "futureCausality", "causality": "vendorPrivate", "variability": "continuous"},
            {"name": "futureVariability", "causality": "input", "variability": "vendorMode"},
        ],
    })

    assert policy["variables"]["futureCausality"] == {"read": False, "writeAt": []}
    assert policy["variables"]["futureVariability"] == {"read": True, "writeAt": []}


def test_provider_policy_can_restrict_but_not_expand_fmi_permissions(metadata):
    policy = build_effective_policy(
        metadata,
        overrides={
            "command": {"read": False, "writeAt": ["initialization"]},
            "speed": {"read": False, "writeAt": []},
        },
    )

    assert policy["variables"]["command"]["writeAt"] == ["initialization"]
    assert policy["variables"]["speed"] == {"read": False, "writeAt": []}

    with pytest.raises(ValueError, match="cannot grant unsupported access"):
        build_effective_policy(
            metadata,
            overrides={"internal": {"read": True, "writeAt": []}},
        )


@pytest.mark.parametrize(
    ("values", "phase"),
    [
        ({"command": 1}, "initialization"),
        ({"gain": 2}, "initialization"),
        ({"command": 1}, "runtime"),
    ],
)
def test_validate_writes_accepts_only_effective_writes(metadata, values, phase):
    validate_writes(build_effective_policy(metadata), values, phase=phase)


@pytest.mark.parametrize(
    ("values", "phase"),
    [
        ({"speed": 5}, "initialization"),
        ({"calibration": 5}, "initialization"),
        ({"gain": 2}, "runtime"),
        ({"missing": 2}, "initialization"),
    ],
)
def test_validate_writes_rejects_unavailable_or_unauthorized_variables(metadata, values, phase):
    with pytest.raises(AccessDenied):
        validate_writes(build_effective_policy(metadata), values, phase=phase)


def test_filter_fmi_values_hides_unreadable_names_in_nested_results(metadata):
    policy = build_effective_policy(metadata)
    payload = {
        "simId": "run-1",
        "outputVariables": ["speed", "internal"],
        "samples": [
            {"time": 0, "outputs": {"speed": 1.5, "computed": 3, "internal": 8}},
            {"time": 1, "outputs": {"speed": 2.5, "computed": 4}},
        ],
        "parameters": {"command": 1},
    }

    assert filter_fmi_values(policy, payload) == {
        "simId": "run-1",
        "outputVariables": ["speed"],
        "samples": [
            {"time": 0, "outputs": {"speed": 1.5, "computed": 3}},
            {"time": 1, "outputs": {"speed": 2.5, "computed": 4}},
        ],
        "parameters": {"command": 1},
    }


def test_model_description_keeps_public_fmi_variables_and_hides_local_variables(metadata):
    policy = build_effective_policy(metadata)
    description = {
        "type": "model.description",
        "modelVariables": [
            {"name": "command", "causality": "input", "start": 2},
            {"name": "speed", "causality": "output", "start": 0},
            {"name": "internal", "causality": "local", "start": 0},
        ],
    }

    filtered = filter_model_description(policy, description)

    assert filtered == {
        "type": "model.description",
        "modelVariables": [
            {"name": "command", "causality": "input", "start": 2},
            {"name": "speed", "causality": "output", "start": 0},
        ],
    }

def test_duplicate_or_invalid_fmi_variable_names_fail_closed(metadata):
    metadata["modelVariables"].append({"name": "command", "causality": "output"})
    with pytest.raises(ValueError, match="duplicate FMI variable name"):
        build_effective_policy(metadata)


def test_validate_reads_allows_outputs_and_rejects_hidden_or_unreadable_names(metadata):
    policy = build_effective_policy(metadata)
    validate_reads(policy, ["speed"])
    validate_reads(policy, None)

    validate_reads(policy, ["command"])
    with pytest.raises(AccessDenied):
        validate_reads(policy, ["internal"])
    with pytest.raises(AccessDenied):
        validate_reads(policy, ["unknown"])


def test_part4_generated_rules_are_exact_fmi_allow_list(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = build_part4_access_rules(metadata, submodel_id)
    policy = compile_part4_access_rules(
        document, metadata, submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={"labId": "42"},
        source="aas-generated",
    )

    assert policy["policySource"] == "aas-generated"
    assert policy["variables"]["speed"] == {"read": True, "writeAt": []}
    assert policy["variables"]["command"] == {
        "read": True,
        "writeAt": ["initialization", "runtime"],
    }
    assert policy["variables"]["gain"] == {"read": True, "writeAt": ["initialization"]}
    assert policy["variables"]["calibration"] == {"read": True, "writeAt": []}
    assert policy["variables"]["internal"] == {"read": False, "writeAt": []}
    assert policy["interfaceDigest"] == fmi_interface_digest(metadata)


def test_part4_custom_rules_restrict_permissions_and_evaluate_verified_claims(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = build_part4_access_rules(metadata, submodel_id)
    document["AllAccessPermissionRules"]["rules"] = [
        {
            "ACL": {"ATTRIBUTES": [{"CLAIM": "institution"}], "RIGHTS": ["READ"], "ACCESS": "ALLOW"},
            "OBJECTS": [{"REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Output.speed'}],
            "FORMULA": {"$eq": [{"$attribute": {"CLAIM": "institution"}}, {"$strVal": "north-campus"}]},
        },
        {
            "ACL": {"ATTRIBUTES": [], "RIGHTS": ["UPDATE"], "ACCESS": "ALLOW"},
            "OBJECTS": [{"REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Input.command'}],
            "FORMULA": {"$boolean": True},
        },
    ]

    allowed = compile_part4_access_rules(
        document, metadata, submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={"institution": "north-campus"},
    )
    restricted = compile_part4_access_rules(
        document, metadata, submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={"institution": "south-campus"},
    )

    assert allowed["variables"]["speed"]["read"] is True
    assert restricted["variables"]["speed"]["read"] is False
    assert restricted["variables"]["command"]["writeAt"] == ["initialization", "runtime"]
    assert restricted["variables"]["gain"]["writeAt"] == []


def test_part4_reusable_definitions_compile_attributes_acl_objects_and_formula(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = {
        "AllAccessPermissionRules": {
            "DEFATTRIBUTES": [
                {"name": "tenant", "attributes": [{"CLAIM": "institution"}]},
                {"name": "authorizedTenant", "USEATTRIBUTES": ["tenant"]},
            ],
            "DEFACLS": [{
                "name": "readForTenant",
                "acl": {
                    "USEATTRIBUTES": "authorizedTenant",
                    "RIGHTS": ["READ"],
                    "ACCESS": "ALLOW",
                },
            }],
            "DEFOBJECTS": [
                {"name": "outputs", "objects": [
                    {"REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Output.speed'},
                ]},
                {"name": "allReadable", "USEOBJECTS": ["outputs"]},
            ],
            "DEFFORMULAS": [{
                "name": "northCampus",
                "formula": {"$eq": [
                    {"$attribute": {"CLAIM": "institution"}},
                    {"$strVal": "north-campus"},
                ]},
            }],
            "rules": [{
                "USEACL": "readForTenant",
                "OBJECTS": [{"REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Parameter.computed'}],
                "USEOBJECTS": ["allReadable"],
                "USEFORMULA": "northCampus",
            }],
        },
    }

    policy = compile_part4_access_rules(
        document,
        metadata,
        submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={"institution": "north-campus"},
    )

    assert policy["variables"]["speed"]["read"] is True
    assert policy["variables"]["computed"]["read"] is True
    assert policy["variables"]["command"]["read"] is False


def test_part4_reusable_definitions_accept_empty_groups_and_combined_rule_objects(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = {
        "AllAccessPermissionRules": {
            "DEFATTRIBUTES": [{"name": "anonymousContext", "attributes": []}],
            "DEFACLS": [{
                "name": "publicRead",
                "acl": {
                    "USEATTRIBUTES": "anonymousContext",
                    "RIGHTS": ["READ"],
                    "ACCESS": "ALLOW",
                },
            }],
            "DEFOBJECTS": [{"name": "emptyObjects", "objects": []}],
            "rules": [{
                "USEACL": "publicRead",
                "OBJECTS": [{
                    "REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Output.speed',
                }],
                "USEOBJECTS": ["emptyObjects"],
                "FORMULA": {"$boolean": True},
            }],
        },
    }

    policy = compile_part4_access_rules(
        document,
        metadata,
        submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={},
    )

    assert policy["variables"]["speed"]["read"] is True


def test_part4_attribute_and_object_groups_can_mix_inline_items_with_references(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = {
        "AllAccessPermissionRules": {
            "DEFATTRIBUTES": [
                {"name": "institution", "attributes": [{"CLAIM": "institution"}]},
                {
                    "name": "eligibleSubject",
                    "attributes": [{"CLAIM": "plan"}],
                    "USEATTRIBUTES": ["institution"],
                },
            ],
            "DEFACLS": [{
                "name": "readSelectedOutputs",
                "acl": {
                    "USEATTRIBUTES": "eligibleSubject",
                    "RIGHTS": ["READ"],
                    "ACCESS": "ALLOW",
                },
            }],
            "DEFOBJECTS": [
                {"name": "primaryOutput", "objects": [{
                    "REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Output.speed',
                }]},
                {
                    "name": "selectedOutputs",
                    "objects": [{
                        "REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Parameter.computed',
                    }],
                    "USEOBJECTS": ["primaryOutput"],
                },
            ],
            "DEFFORMULAS": [{
                "name": "eligible",
                "formula": {"$and": [
                    {"$eq": [
                        {"$attribute": {"CLAIM": "institution"}},
                        {"$strVal": "north-campus"},
                    ]},
                    {"$eq": [
                        {"$attribute": {"CLAIM": "plan"}},
                        {"$strVal": "education"},
                    ]},
                ]},
            }],
            "rules": [{
                "USEACL": "readSelectedOutputs",
                "USEOBJECTS": ["selectedOutputs"],
                "USEFORMULA": "eligible",
            }],
        },
    }

    policy = compile_part4_access_rules(
        document,
        metadata,
        submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={"institution": "north-campus", "plan": "education"},
    )

    assert policy["variables"]["speed"]["read"] is True
    assert policy["variables"]["computed"]["read"] is True


def test_part4_disabled_acl_is_ignored_without_granting_access(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = {
        "AllAccessPermissionRules": {
            "rules": [{
                "ACL": {"ATTRIBUTES": [], "RIGHTS": ["READ"], "ACCESS": "DISABLED"},
                "OBJECTS": [{"REFERABLE": f'$sme("{submodel_id}").SimulationModel.Ports.Output.speed'}],
                "FORMULA": {"$boolean": True},
            }],
        },
    }

    policy = compile_part4_access_rules(
        document,
        metadata,
        submodel_id,
        declared_interface_digest=fmi_interface_digest(metadata),
        claims={},
    )

    assert policy["variables"]["speed"]["read"] is False


@pytest.mark.parametrize(
    "definitions",
    [
        {"DEFATTRIBUTES": [{"name": "a", "USEATTRIBUTES": ["b"]}, {"name": "b", "USEATTRIBUTES": ["a"]}]},
        {"DEFOBJECTS": [{"name": "a", "USEOBJECTS": ["missing"]}]},
        {"DEFACLS": [{"name": "same", "acl": {"ATTRIBUTES": [], "RIGHTS": ["READ"], "ACCESS": "ALLOW"}}, {"name": "same", "acl": {"ATTRIBUTES": [], "RIGHTS": ["READ"], "ACCESS": "ALLOW"}}]},
        {"DEFFORMULAS": [{"name": "formula", "formula": {"$boolean": "yes"}}]},
    ],
)
def test_part4_malformed_or_cyclic_reusable_definitions_fail_closed(metadata, definitions):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = {"AllAccessPermissionRules": {**definitions, "rules": []}}

    with pytest.raises(ValueError):
        compile_part4_access_rules(
            document,
            metadata,
            submodel_id,
            declared_interface_digest=fmi_interface_digest(metadata),
            claims={},
        )


@pytest.mark.parametrize(
    ("version", "simulation_type", "expected_runtime"),
    [
        ("2.0", "CoSimulation", True),
        ("2.0", "ModelExchange", False),
        ("3.0", "CoSimulation", True),
        ("3.0", "ModelExchange", False),
    ],
)
def test_tunable_parameter_runtime_write_matrix(version, simulation_type, expected_runtime):
    policy = build_effective_policy({
        "fmiVersion": version,
        "simulationType": simulation_type,
        "modelVariables": [
            {"name": "tunable", "causality": "parameter", "variability": "tunable"},
            {"name": "fixed", "causality": "parameter", "variability": "fixed"},
        ],
    })

    assert ("runtime" in policy["variables"]["tunable"]["writeAt"]) is expected_runtime
    assert "runtime" not in policy["variables"]["fixed"]["writeAt"]


def test_external_part4_profile_can_use_an_explicit_simulation_submodel_without_gateway_digest(metadata):
    simulation_submodel_id = "urn:partner:aas:simulation-models"
    document = build_part4_access_rules(metadata, simulation_submodel_id)

    policy = compile_part4_access_rules(
        document,
        metadata,
        None,
        declared_interface_digest=None,
        claims={"labId": "42"},
        source="aas-provider",
        allowed_submodel_ids={simulation_submodel_id},
    )

    assert policy["policySource"] == "aas-provider"
    assert policy["variables"]["speed"]["read"] is True

    with pytest.raises(ValueError, match="unknown FMI variable"):
        compile_part4_access_rules(
            document,
            metadata,
            None,
            declared_interface_digest=None,
            claims={"labId": "42"},
            source="aas-provider",
            allowed_submodel_ids={"urn:partner:aas:other-submodel"},
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc, sm: doc["AllAccessPermissionRules"].update(unexpected=True),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"].append({"ACL": {"ATTRIBUTES": [], "RIGHTS": ["UPDATE"], "ACCESS": "ALLOW"}, "OBJECTS": [{"REFERABLE": f'$sme("{sm}").SimulationModel.Ports.Output.speed'}], "FORMULA": {"$boolean": True}}),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"][0]["OBJECTS"][0].update(ROUTE="*"),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"][0].update(FILTER={"FRAGMENT": "*"}),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"][0].update(FORMULA={"$regex": []}),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"][0].update(FORMULA={"$strVal": "truthy is not a boolean"}),
        lambda doc, sm: doc["AllAccessPermissionRules"]["rules"][0].update(FORMULA={"$and": [{"$strVal": "truthy is not a boolean"}]}),
    ],
)
def test_part4_invalid_or_expansive_rules_fail_closed(metadata, mutate):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = build_part4_access_rules(metadata, submodel_id)
    mutate(document, submodel_id)

    with pytest.raises(ValueError):
        compile_part4_access_rules(
            document, metadata, submodel_id,
            declared_interface_digest=fmi_interface_digest(metadata), claims={},
        )


def test_part4_boolean_and_or_operators_match_the_minimum_arity(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = build_part4_access_rules(metadata, submodel_id)
    document["AllAccessPermissionRules"]["rules"][0]["FORMULA"] = {
        "$and": [{"$boolean": True}],
    }

    with pytest.raises(ValueError, match="boolean expression"):
        compile_part4_access_rules(
            document,
            metadata,
            submodel_id,
            declared_interface_digest=fmi_interface_digest(metadata),
            claims={},
        )


def test_part4_rules_reject_stale_fmi_interface(metadata):
    submodel_id = "urn:decentralabs:lab:42:sm:simulationModels"
    document = build_part4_access_rules(metadata, submodel_id)
    changed = {**metadata, "modelVariables": [*metadata["modelVariables"], {"name": "new", "causality": "output"}]}

    with pytest.raises(ValueError, match="stale"):
        compile_part4_access_rules(
            document, changed, submodel_id,
            declared_interface_digest=fmi_interface_digest(metadata), claims={},
        )
