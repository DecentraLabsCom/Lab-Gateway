# Station Contract

This directory is the canonical, platform-neutral station contract consumed by
Lab Gateway, Lab Station for Windows, and Lab Station Linux.

- `v2/` freezes representative Windows payloads for the compatibility adapter.
- `v3/` defines the common status/heartbeat, capabilities, and command result
  schemas. Platform-specific details belong under `platformSpecific`.
- `dispatcher/v1/` and `dispatcher/v2/` define the SSH request envelopes.
  Dispatcher v2 also defines the correlated response shape and success/warning/
  failure fixtures. The dispatcher protocol is independent of the status
  contract version.

Consumers must normalize payloads once at ingress. Reservation, readiness,
timeline, AAS, and public status code use the normalized model and must not
inspect Windows paths or transport-specific heartbeat fields.

`summary.ready` and `summary.issues` describe the profile's primary capability:
`readiness.physicalLab` for `dedicated` and `hybrid`, and `readiness.fmu` for
`fmu-only`. Wake and optional FMU readiness remain separate capabilities.
Consumers that need a specific capability must read its `readiness` entry.

## Profile-gated operator actions

The normalized profiles have the same operator meaning on Windows and Linux:

| Profile | Prepare / Release | Enable Local |
| --- | --- | --- |
| `dedicated` | Supported for the physical lab. Prepare fails closed if session inventory is unavailable or an unexpected local console session is active. | Not available. Disable remains available only to clear an already active stale flag. |
| `hybrid` | Supported for the physical lab. Prepare refuses active or unknown local mode and unavailable session inventory. When enabled by the Station policy, it warns and waits before evicting an eligible local console session; when disabled it fails safely. Prepare also clears bounded user working data and FMU temporary state. Release closes only the managed remote lab-user session. | Supported for instructor on-site use when no reservation or remote lab-user session is active. It expires after eight hours by default on current Windows and Linux Stations. |
| `fmu-only` | Not supported. | Not supported. Disable remains available only to clear an already active stale flag. |

Both agents expire local mode only from a valid explicit expiry or a recognized
legacy timestamp. A malformed or marker-only flag stays active until an
operator clears it; file modification time is not treated as proof of expiry.

The Gateway checks a fresh Station status and a successful session inventory
before manual Prepare, Release, or Enable Local requests. Current Station
agents also enforce the profile rules and serialize local-mode enable against
reservation operations, so using WinRM or SSH does not change the action's
meaning. Disabling local mode is allowed for cleanup even if the profile has
since changed.

Both Station agents attempt to release an active reservation lease locally
when `expiresAt` passes, even if Gateway cannot send the normal release
request. Windows runs this watchdog in its setup-managed background task;
Linux runs it in `labstationd`. If cleanup fails, the station stays closed to
new leases for operator reconciliation.

Dispatcher v2 is negotiated through authenticated Station identity before
Gateway sends a lease-bound lifecycle request. SSH and WinRM use the same
durable operation flow: query `operation.status` before sending, keep the same
operation ID for retries, and query again after an uncertain transport result.
A `recovery-required` result is a classified failure and must not be sent
again automatically.
