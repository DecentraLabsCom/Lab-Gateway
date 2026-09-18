import host_inventory_values


def test_safe_host_inventory_entry_contains_public_trust_and_operational_fields():
    host = {
        "name": "lab-ws-01",
        "address": "192.168.1.50",
        "credential_ref": "station-01",
        "mac": "00:11:22:33:44:55",
        "broadcast": "192.168.1.255",
        "labs": [1, "2"],
        "mode": "pure",
    }
    trust = {
        "trustRef": "station-01",
        "configured": True,
        "status": "ready",
        "fingerprintSha256": "abc",
        "sanDnsNames": ["station-01"],
        "sanIpAddresses": ["192.168.1.50"],
    }

    result = host_inventory_values.safe_host_inventory_entry(
        host,
        editable=True,
        credential_ref_for_host=lambda received_host: received_host["credential_ref"],
        inspect_winrm_trust=lambda _host: trust,
        winrm_credentials_configured=lambda ref: ref == "station-01",
        default_heartbeat_path=r"C:\LabStation\heartbeat.json",
    )

    assert result["credentialRef"] == "station-01"
    assert result["winrmTrustStatus"] == "ready"
    assert result["winrmTrustFingerprintSha256"] == "abc"
    assert result["heartbeatPath"] == r"C:\LabStation\heartbeat.json"
    assert result["labstationPath"] == r"C:\Lab Station"
    assert result["broadcast"] == "192.168.1.255"
    assert "stationPathsReady" not in result
    assert "stationPathIssues" not in result
    assert "labs" not in result
    assert result["editable"] is True
    assert result["winrmConfigured"] is True


def test_safe_host_inventory_entry_does_not_expose_inline_credentials():
    result = host_inventory_values.safe_host_inventory_entry(
        {
            "name": "lab-ws-01",
            "address": "192.168.1.50",
            "winrm_user": "user",
            "winrm_pass": "password",
        },
        credential_ref_for_host=lambda _host: "station-01",
        inspect_winrm_trust=lambda _host: {},
        winrm_credentials_configured=lambda _ref: False,
        default_heartbeat_path="heartbeat-default",
    )

    assert "winrm_user" not in result
    assert "winrm_pass" not in result
    assert result["winrmConfigured"] is True
