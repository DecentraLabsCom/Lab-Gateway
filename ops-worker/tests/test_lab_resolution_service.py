from lab_resolution_service import (
    extract_lab_catalog,
    resolve_lab_associations,
    resolve_host_for_lab,
    resolve_lab_access_key,
    resolve_lab_ids_for_host,
    resolve_lab_resources,
    resolve_lab_status_targets,
)


LABS = [
    {"labId": "lab-1", "accessKey": "guac:id:5", "resourceType": 0},
    {"labId": "lab-2", "accessKey": "guac:id:6", "resourceType": 0},
    {"labId": "fmu-1", "accessKey": "fmu:file:1", "resourceType": 1},
]

CONNECTIONS = [
    {"id": 5, "hostname": "station-01", "protocol": "rdp", "port": "3389"},
    {"id": 6, "hostname": "192.168.1.52", "protocol": "ssh", "port": "22"},
    {"id": 9, "hostname": "linux-only", "protocol": "ssh", "port": "22"},
]

HOSTS = [
    {"name": "station-01", "address": "192.168.1.51"},
    {"name": "station-02", "address": "192.168.1.52"},
]


def _parse_selector(value):
    prefix, identifier = str(value).split(":id:", 1)
    assert prefix == "guac"
    return int(identifier)


def _normalize(value):
    return str(value or "").strip().lower()


def test_extract_lab_catalog_accepts_backend_envelope_and_discards_invalid_rows():
    assert extract_lab_catalog({"labs": LABS + [None, {"name": "missing-id"}]}) == LABS
    assert extract_lab_catalog([]) == []


def test_resolve_lab_access_key_reads_catalog_entry_without_host_config():
    assert resolve_lab_access_key(LABS, "lab-1") == "guac:id:5"
    assert resolve_lab_access_key(LABS, "missing") is None


def test_resolve_lab_resources_preserves_fmu_type_without_guacamole_mapping():
    assert resolve_lab_resources(LABS) == [
        {"labId": "lab-1", "resourceType": "lab"},
        {"labId": "lab-2", "resourceType": "lab"},
        {
            "labId": "fmu-1",
            "resourceType": "fmu",
            "executionBackend": "station",
        },
    ]


def test_resolve_lab_resources_allows_explicit_local_fmu_execution_and_station_host():
    labs = [{
        "labId": "fmu-local",
        "resourceType": 1,
        "executionBackend": "local",
    }, {
        "labId": "fmu-station",
        "resourceType": 1,
        "executionBackend": "station",
        "stationHostName": "station-01",
    }]

    assert resolve_lab_resources(labs) == [
        {
            "labId": "fmu-local",
            "resourceType": "fmu",
            "executionBackend": "local",
        },
        {
            "labId": "fmu-station",
            "resourceType": "fmu",
            "executionBackend": "station",
            "stationHostName": "station-01",
        },
    ]


def test_resolve_host_for_lab_follows_lab_access_key_connection_and_hostname():
    assert resolve_host_for_lab(
        LABS,
        "lab-1",
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) == HOSTS[0]
    assert resolve_host_for_lab(
        LABS,
        "fmu-1",
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) is None


def test_resolve_host_for_lab_fails_closed_for_ambiguous_hostname():
    duplicate_hosts = HOSTS + [{"name": "station-01-copy", "address": "station-01"}]
    assert resolve_host_for_lab(
        LABS,
        "lab-1",
        CONNECTIONS,
        duplicate_hosts,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) is None


def test_resolve_lab_ids_for_host_inverts_the_same_catalog_mapping():
    assert resolve_lab_ids_for_host(
        LABS,
        HOSTS[0],
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) == ["lab-1"]
    assert resolve_lab_ids_for_host(
        LABS,
        HOSTS[1],
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) == ["lab-2"]


def test_resolve_lab_associations_projects_only_resolved_lab_and_host_ids():
    assert resolve_lab_associations(
        LABS,
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) == [
        {"labId": "lab-1", "hostName": "station-01"},
        {"labId": "lab-2", "hostName": "station-02"},
    ]


def test_resolve_lab_status_targets_keeps_guacamole_only_connections():
    labs = LABS + [{"labId": "linux-only-lab", "accessKey": "guac:id:9"}]

    assert resolve_lab_status_targets(
        labs,
        CONNECTIONS,
        HOSTS,
        parse_selector=_parse_selector,
        normalize_key=_normalize,
    ) == [
        {
            "labId": "lab-1",
            "connectionId": "5",
            "hostname": "station-01",
            "protocol": "rdp",
            "port": "3389",
            "hostName": "station-01",
        },
        {
            "labId": "lab-2",
            "connectionId": "6",
            "hostname": "192.168.1.52",
            "protocol": "ssh",
            "port": "22",
            "hostName": "station-02",
        },
        {
            "labId": "linux-only-lab",
            "connectionId": "9",
            "hostname": "linux-only",
            "protocol": "ssh",
            "port": "22",
        },
    ]
