# Lab Station Session and Action Matrix

## Terms

- **Local session:** An interactive session on the physical Windows console or a local Linux seat. This includes a local session for `LABUSER`/`labuser`.
- **Remote LABUSER session:** A Windows RemoteApp/RDP or Linux XRDP/Tiny Desk session using the managed `LABUSER`/`labuser` account.
- **Other remote account:** A remote session that does not use the managed account. The session inventory classifies it as remote, but Prepare rules do not treat it the same as a remote LABUSER session.
- **Administrative action:** An operator command with no reservation/demo context. It does not create or release a lease.
- **Lease-bound action:** A Dispatcher v2 command carrying the identity, generation, and time window of a reservation or demo lease.
- **Station lease:** Operational state persisted by the Station. A confirmed reservation, remote connection, or Marketplace state does not create a lease by itself; the Station records it when it accepts a contextual Prepare.

## Behavior by profile and platform

| Profile | Windows | Linux | Effective access priority |
| --- | --- | --- | --- |
| `dedicated` | Prepare warns every active console session and, after the configured grace period, logs it off without asking for confirmation. This includes `LABUSER` and other local accounts. Windows setup normally denies local sign-in to most non-exempt accounts; if one is active, the same handoff applies. | Prepare broadcasts a warning to local sessions and, after the configured grace period, logs them off without asking for confirmation. This includes `labuser` and other local accounts. | A reservation takes precedence over every local session. `local-mode` is unavailable. |
| `hybrid` | Allows interactive local sign-in. With `local-mode` active, Prepare is rejected; otherwise eligible local sessions must confirm when `AllowLocalSessionEviction` is enabled. | Same policy; Linux uses `loginctl` and its local-session confirmation flow. | Sequential handoff, not guaranteed simultaneous use. `local-mode` protects declared local use; without it, remote access can request a handoff. |
| `fmu-only` | Not supported as a physical profile for Prepare/Release. | Does not install Tiny Desk and does not support physical Prepare/Release. | Outside this physical-access matrix. |

Windows identifies its physical console as local and its RemoteApp/RDP sessions as remote. Linux uses the `loginctl` seat for local sessions and classifies XRDP/Tiny Desk sessions as remote. Both classifications apply regardless of account, so a remote session under another account does not set `localSessionActive`.

## Prepare matrix

The profile columns apply to both Windows and Linux unless a platform difference is called out. Both the Gateway and the Station agent fail safely when they cannot verify a required value.

| Condition when preparing | `dedicated` | `hybrid` | Does Prepare continue? |
| --- | --- | --- | --- |
| No local session; the profile's local-mode guard is satisfied; inventory known | Continues if all other checks pass; Dedicated does not support local mode. | Continues if all other checks pass; Hybrid requires local mode off. | Yes; Prepare cleans the managed environment and FMU Executor state first. |
| Local LABUSER session | Sends a warning, waits through the configured grace period, then logs off the session without a confirmation prompt. | With `AllowLocalSessionEviction=true` and local mode off, shows this session a graphical Allow/Deny prompt. Allow proceeds with the handoff; Deny, timeout, or an unavailable prompt cancels Prepare and leaves the session open. If eviction is disabled, Prepare rejects without prompting. | Dedicated proceeds after the warning and grace period. Hybrid proceeds only when every eligible local session allows the handoff; a denial or timeout cancels it. |
| Local session for another account | Same behavior as for local LABUSER. | Same behavior as for local LABUSER. | Same profile-specific outcome as above; changed or unknown inventory fails before further logoff. |
| Warning cannot be sent to every local session | Dedicated fails before logoff. | Same Dedicated behavior; Hybrid keeps its confirmation flow. | No silent Dedicated handoff. |
| `local-mode` active or state unknown | Dedicated does not support local mode and treats any stale marker as disabled; Hybrid rejects. | Same behavior. | Dedicated proceeds; Hybrid fails closed. A malformed Hybrid marker remains active until explicitly cleared. |
| Session inventory unknown or inconsistent | Rejects before handoff. | Same behavior. | No; inventory must be complete. |
| Remote LABUSER session; another mapped-lab reservation is active, reservation state is unknown, or the incoming reservation already has access-session evidence | Rejects before handoff, even if the Station lease is missing. | Same behavior. | No; active or unverified access remains protected. |
| Remote LABUSER session; no conflicting reservation or access-session evidence | Same handoff as a local LABUSER session: warn, wait the configured grace period, then log off without confirmation. | Same confirmation policy as a local LABUSER session: the eligible session must allow eviction; denial or timeout cancels Prepare. | Yes. Gateway passes the observed session IDs; the Station rechecks them before handoff and cleanup. |
| Remote session under another account, with no active lease | Not included in Prepare's handoff; remains connected. | Same behavior. | Prepare may continue without closing it; shared FMU Executor cleanup may interrupt its work. |
| Lease active, being prepared, or requiring recovery | Administrative Prepare is rejected. | Same behavior. | Contextual Prepare requires no other active lease or pending recovery; identity and generation prevent overlap. |
| `AllowLocalSessionEviction=false` with a local session | Dedicated still warns and hands off; Hybrid follows this setting. | Same behavior. | The setting affects Hybrid only. |

In Hybrid, the warning requires affirmative confirmation; it is not an informational message that permits automatic eviction. Dedicated must successfully send an informational warning to every active local session and observes the configured grace period; `--no-guard` and silent-notification options do not bypass that handoff. If any warning cannot be sent, Prepare fails before logging off a local session. A Dedicated local user has no accept/decline choice. Hybrid retains its existing confirmation and explicit `--no-guard` behavior.

### Administrative Prepare versus lease-bound Prepare

| Route | Authorization and guards | Lease outcome |
| --- | --- | --- |
| Administrative/manual | Uses the administrative channel. Requires no active Station lease, a known session inventory, and no active or imminent reservation for the Station's mapped labs if a remote LABUSER session is present. With authoritative proof that no such reservation is active, it applies the profile's session handoff. Hybrid also requires local mode off; Dedicated ignores/clears stale local-mode state. | Does not create a reservation lease or authorize the remote user to connect. |
| Reservation or demo | Requires a valid Dispatcher v2 envelope. Station rejects another active or recovery lease. Any other active reservation for a mapped lab, unknown reservation state, or an unexpired access token/previous successful Prepare for the incoming reservation protects remote LABUSER. If the incoming reservation is the only active reservation and has no access-session evidence, Prepare applies the profile's session handoff to the reported remote IDs. | When Prepare is accepted, Station records the lease and its generation. Success or a non-fatal warning may leave it active; incomplete cleanup or an uncertain result may leave it in `recovery-required`. The connection/reservation alone does not create this state. |

The Gateway checks the authoritative reservation projection for every lab mapped to the Station. For lease-bound Prepare it also checks access-session evidence for the incoming reservation; any other active/imminent reservation or uncertain projection blocks the handoff. An incoming reservation with no prior successful Prepare or unexpired access token may take over a residual session. Gateway passes the exact observed session IDs in a managed argument. Windows and Linux compare those IDs with the live OS session inventory before warning, after the grace/confirmation flow, before each logoff, and before cleanup. A missing Station lease alone never authorizes the handoff. Administrative Release remains separate and protects every remote LABUSER session.

On Windows, disconnected RDP sessions remain in `remoteLabUserSessionIds` and can be included in the authorized handoff. On Linux, a disconnected XRDP session continues to count while `loginctl` lists it as a Tiny Desk `labuser` session.

## Release matrix

Release effects depend on the Station profile; the variants differ in authorization and which lease state they can modify.

| Variant | Windows | Linux | Lease effect |
| --- | --- | --- | --- |
| Administrative, no active lease | Requires no lease or remote LABUSER session; may clean FMU Executor state. | Same policy. | Does not modify a lease. If a lease or remote LABUSER session is active, use the matching reservation Release. |
| Reservation/demo-bound | Requires the matching active lease and generation; closes managed LABUSER RDP sessions. | Same policy; closes managed `labuser` XRDP/Tiny Desk sessions. | Gateway builds context from Prepare. Success releases the lease; failed or uncertain cleanup leaves it `recovery-required` and blocks new work. |
| Local watchdog on `expiresAt` | Background task runs lease-bound Release. | Same behavior; `labstationd` runs it. | Fresh-ID retries every 60 seconds after failed Release, including before expiry. Failed Prepare waits until expiry. Attempts require valid lease identity, local mode off, known inventory, and no protected sessions. Scheduled Gateway retries use the same guard; neither path replays an uncertain ID. |

| Sessions present during Release | Result for both Windows and Linux variants |
| --- | --- |
| Physical local console, any account | Dedicated logs off active local accounts other than LABUSER and preserves local LABUSER; Hybrid preserves local console sessions. Shared FMU Executor cleanup may still interrupt local FMU work. |
| Remote LABUSER session, active lease | Only the matching lease-bound Release may close it. Administrative Release is rejected. |
| Remote LABUSER session, no active lease | Administrative Release is also rejected because the Station cannot prove that the session is unreserved. The user must disconnect or an operator must end the OS session explicitly; FMU cleanup is not run by administrative Release. |
| Remote session under another account | It is not logged off. Shared FMU Executor cleanup may still interrupt FMU work performed by that session. |
| Session inventory unavailable | Release fails before cleanup completes. On the lease-bound route, state may become `recovery-required`; automatic reconciliation waits and retries after 60 seconds until the inventory is known. |

Windows accepts an explicit `--user=<account>` command parameter and can close another account's RDP session if the operator requests it; normal routes use LABUSER. Linux does not accept that parameter for Release and always targets `labuser`.

Release does not reboot the computer by default. If `--reboot` is explicitly requested, the internal check waits for local sessions and the managed remote LABUSER session to end; it does not check all other remote accounts in the same way. Gateway's `power shutdown/hibernate` policy is stricter: it requires local mode off, a complete inventory, and no active user sessions, local or remote.

## Effective priority by active session

| Existing use | Administrative Prepare | Reservation/lease Prepare | Administrative or lease Release |
| --- | --- | --- | --- |
| LABUSER at the local console | Dedicated warns then hands off after grace; Hybrid follows local-mode and confirmation rules. | Same policy for both Prepare routes. | Preserves the local session; shared FMU cleanup may affect it. |
| Another account at the local console | Same profile-specific behavior as above. | Same behavior. | Dedicated logs off the session; Hybrid preserves it. Shared FMU Executor cleanup may still affect its work. |
| Remote LABUSER with an active lease | Rejected because a lease is active. | A second Prepare is rejected because the lease already exists. | Administrative Release is rejected. A matching lease Release can close the session and finish the lease. |
| Residual remote LABUSER, no active lease | Prepare is rejected if Gateway cannot prove the session is unreserved; with authoritative proof, it follows the profile-specific handoff. Administrative Release stays blocked. | Same behavior. | Contextual Release requires a matching lease; administrative Release cannot close an unleased remote LABUSER session. |
| Remote session under another account, no active lease | Not included in Prepare's handoff; it remains connected and Prepare may continue. | Same behavior. | It is not logged off; shared FMU Executor cleanup may still affect its work. |

## Related controls and limits

- **Local mode:** Can only be enabled in Hybrid, with a known inventory, no active Station lease, and no remote LABUSER session. The current Station Contract v3 path does not query Gateway's authoritative reservation projection, so operators should enable it outside active reservation windows. Current configurations default to an eight-hour expiration. Enabling it blocks Hybrid Prepare but not Release; Release does not clear it. Dedicated status and Prepare treat local mode as unavailable and clear/ignore stale markers. Clearing local mode remains available on any profile.
- **Shutdown/hibernate:** Does not use the same session exception as Prepare. Gateway requires the Station to advertise the shutdown guard and blocks the request when `local-mode` is active or unknown, the inventory is unreliable, or any user session is active. Station checks again after the configured delay.
- **`evictable` field:** Must not be used as a substitute for the Prepare decision. Hybrid depends on `AllowLocalSessionEviction`, `local-mode`, and confirmation. Dedicated warns and automatically hands off every local session. General Windows telemetry may mark local LABUSER as non-evictable while the Prepare-specific guard can release it; Linux reports local seat sessions as evictable.
- **Concurrent connections:** Remote sessions under other account names are not included in Prepare's handoff and remain connected; shared FMU Executor cleanup may still affect their work.
- **Linux support:** The agent README currently declares `supportTier: unverified` and prerelease status; session classification depends on the information provided by `loginctl` and the installed desktop environment.

## Compliance with the clarified priority rules

The current behavior is:

- For a Dedicated reservation, remote admission and Prepare take precedence over all local sessions. Every local session receives an informational warning and grace period, then is logged off without an accept/decline prompt.
- For a Hybrid station, `local-mode` protects declared on-site use and blocks Prepare. With it off, normal Prepare is turn-based: when eviction is enabled, each eligible local session can accept or decline the handoff; a decline or timeout leaves that session open and aborts Prepare. If eviction is disabled, Prepare is rejected.
- Once remote LABUSER is serving a reservation, unrelated access attempts and Prepare, Release, or Enable Local actions must not close that session or disturb its active reservation lease. Only the matching lease-bound Release for that same reservation and generation may close it as part of normal reservation teardown. Administrative Release, a competing Prepare, and Enable Local must be rejected while the reservation lease is active.
- A remote LABUSER session is protected when Gateway cannot prove it is unreserved. Administrative Prepare requires no active/imminent reservation for any mapped lab; reservation-bound Prepare may take over a residual session only when its incoming reservation is the sole active/imminent one and has no prior access-session evidence. Unknown reservation state blocks handoff.
- Administrative Release never closes a remote LABUSER session, even when no Station lease is recorded. A missing lease does not prove the session is unreserved; only a matching lease-bound Release may close a reserved remote session.
- `local-mode` is Hybrid-only. It cannot be enabled while a remote LABUSER session or Station lease is active, and active local-mode blocks Hybrid Prepare.
- Handoffs fail closed when session inventory is unknown or changes. Gateway authorizes the exact observed remote LABUSER session IDs; the Station rechecks them during handoff and stops before further logoff or cleanup if a new or changed session appears.

| Situation | Required behavior | Current Windows and Linux behavior | Compliance |
| --- | --- | --- | --- |
| Dedicated Prepare with any local session | Warn, wait grace, then log off without confirmation; do not log off if notification fails. | Same behavior. | **Yes.** |
| Dedicated Prepare with `local-mode` active or unknown | Ignore or clear stale state; it must not block remote Prepare. | Same behavior; Gateway skips the Hybrid-only preflight. | **Yes.** |
| Competing reservation actions while a lease is active | Other Prepare, administrative Release, mismatched Release, and Enable Local must not interrupt the reserved remote LABUSER session. Matching Release may end it. | Enforced across Gateway preflight and Station lease identity/generation checks. | **Yes for active-lease command paths.** |
| Remote LABUSER session associated with another active reservation, uncertain reservation state, or an incoming reservation with prior access evidence | Protect it from new Prepare and administrative Release. | Gateway checks the mapped-lab reservation projection and access evidence; the Station lease alone is not used as proof. | **Yes.** |
| Residual remote LABUSER session with no conflicting reservation or access evidence | For Prepare, apply the same profile-specific handoff as for a local LABUSER session. Administrative Release remains separate. | Gateway authorizes the exact session IDs; both Station agents perform and recheck the profile-specific handoff. | **Yes.** |
| Local non-LABUSER session during Release | Dedicated logs off active local console sessions before FMU cleanup. Hybrid preserves local sessions; automatic Hybrid release waits until they end. | Windows and Linux Dedicated Releases log off these sessions for matching reservation and administrative Release. Local LABUSER sessions remain protected. | **Yes.** |

Dedicated local handoff and Release cleanup are enforced on both platforms. A local non-LABUSER session does not make a Dedicated station Busy; local LABUSER and remote sessions retain their existing occupancy behavior. The conditional rule for an unleased remote LABUSER session uses the Gateway reservation projection and a Gateway-managed snapshot of the session IDs; the local lease journal alone cannot establish that no reservation is active. Remote sessions under other accounts remain outside this change and are not included in the LABUSER handoff.

An unknown or inconsistent session inventory still fails closed because the Station cannot reliably notify and release the local sessions. Hybrid fails closed when local-mode state is unknown; Dedicated ignores local-mode state because the profile does not support that feature.

Hybrid supports turn-based combined use: local mode protects declared on-site use; without it, remote access can request a handoff with a warning and confirmation if eviction is enabled. Without `local-mode`, on-site use has no guarantee of indefinite priority.

## Implementation references

- Gateway: `ops-worker/station_action_policy.py`, `ops-worker/station_shutdown_policy.py`, `ops-worker/reservation_operations.py`, `ops-worker/station_lease.py`, `web/assets/js/lab-manager-host-renderers.js`.
- Windows: `Lab Station/labstation/service/SessionManager.ahk`, `SessionGuard.ahk`, `LeaseDispatcher.ahk`, `diagnostics/Status.ahk`, `system/AccountManager.ahk`, `setup/Wizard.ahk`.
- Linux: `Lab Station Linux/internal/agent/agent.go`, `internal/agent/lease.go`, `internal/host/runtime.go`, `internal/config/config.go`, `contracts/station/gateway-contracts/README.md`.
- Related operational description: `gateway-lab-station-operations.md`.
