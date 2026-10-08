"""Container E2E for Gateway's SSH transport and the real Linux dispatcher."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import paramiko

import transports.ssh as ssh_module
from station_ssh_trust import confirm_ssh_host_key, probe_ssh_host_key
from station_transport_factory import StationTransportRuntime
from transports.ssh import SshTransport


def main() -> None:
    private_key = Path("/run/e2e/gateway").read_text(encoding="ascii")
    ssh_module.load_ssh_credential = lambda _reference: {
        "username": "labstation-ops",
        "privateKey": private_key,
    }

    host = {
        "name": "linux-station-e2e",
        "address": "linux-station",
        "management": {
            "transport": "ssh",
            "port": 2222,
            "credentialRef": "gateway-e2e",
            "trustRef": "linux-station-e2e",
        },
    }
    preview = probe_ssh_host_key(host, timeout=5)
    confirm_ssh_host_key(host, preview["fingerprint"], timeout=5)
    runtime = StationTransportRuntime(
        run_winrm_command=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("WinRM was called")),
        read_winrm_file=lambda *_args: "",
        write_winrm_file=lambda *_args: None,
        remove_winrm_file=lambda *_args: None,
        ssh_transport=SshTransport(connect_timeout=5, command_timeout=30),
    )

    identity = runtime.probe(host)
    assert identity["reachable"] is True
    assert identity["transport"] == "ssh"
    assert identity["identity"]["contractVersion"] == "3.0.0"
    assert "reservation-lease-v1" in identity["identity"]["capabilities"]

    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = (now - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    execute_before = (now + timedelta(minutes=4)).isoformat().replace("+00:00", "Z")
    not_before = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    context = {
        "kind": "reservation",
        "labId": "lab-e2e",
        "reservationKey": "reservation-e2e",
        "leaseId": "lease-e2e-1",
        "generation": 0,
        "notBefore": not_before,
        "expiresAt": expires_at,
    }
    prepare_request = {
        "requestId": "e2e-prepare-1",
        "issuedAt": issued,
        "executeBefore": execute_before,
        "context": context,
        "timeoutSeconds": 45,
    }
    prepare = runtime.execute(
        host,
        "prepare-session",
        ["--no-guard"],
        request_id=prepare_request["requestId"],
        dispatcher_request=prepare_request,
    )
    assert prepare["exitCode"] == 0, prepare
    assert prepare["metadata"]["lease"] == {
        "leaseId": "lease-e2e-1",
        "generation": 1,
        "state": "active",
        "expiresAt": expires_at,
    }

    retried_prepare = runtime.execute(
        host,
        "prepare-session",
        ["--no-guard"],
        request_id=prepare_request["requestId"],
        dispatcher_request=prepare_request,
    )
    assert retried_prepare["exitCode"] == 0
    assert retried_prepare["metadata"]["lease"]["generation"] == 1

    release_context = {**context, "generation": 1}
    release_request = {
        "requestId": "e2e-release-1",
        "issuedAt": issued,
        "executeBefore": execute_before,
        "context": release_context,
        "timeoutSeconds": 45,
    }
    release = runtime.execute(
        host,
        "release-session",
        [],
        request_id=release_request["requestId"],
        dispatcher_request=release_request,
    )
    assert release["exitCode"] == 0, release
    assert release["metadata"]["lease"]["state"] == "released"
    assert release["metadata"]["lease"]["generation"] == 1

    retried_release = runtime.execute(
        host,
        "release-session",
        [],
        request_id=release_request["requestId"],
        dispatcher_request=release_request,
    )
    assert retried_release["exitCode"] == 0
    assert retried_release["metadata"]["lease"]["state"] == "released"
    print(json.dumps({"result": "passed", "station": identity["identity"]["host"], "generation": 1}))


if __name__ == "__main__":
    main()
