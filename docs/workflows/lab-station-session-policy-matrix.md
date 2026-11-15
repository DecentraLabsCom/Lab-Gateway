# Lab Station Session and Action Matrix

**Review status:** November 15, 2026. This describes behavior observed in the current Lab Gateway, Lab Station for Windows, and Lab Station for Linux code and contracts. This is a static review; it does not validate every installation or desktop environment.

## Terms

- **Local session:** An interactive session on the physical Windows console or a local Linux seat. This includes a local session for `LABUSER`/`labuser`.
- **Remote LABUSER session:** A Windows RDP or Linux XRDP/Tiny Desk session using the managed `LABUSER`/`labuser` account.
- **Other remote account:** A remote session that does not use the managed account. The session inventory classifies it as remote, but Prepare rules do not treat it the same as a remote LABUSER session.
- **Administrative action:** An operator command with no reservation/demo context. It does not create or release a lease.
- **Lease-bound action:** A Dispatcher v2 command carrying the identity, generation, and time window of a reservation or demo lease.
- **Station lease:** Operational state persisted by the Station. A confirmed reservation, remote connection, or Marketplace state does not create a lease by itself; the Station records it when it accepts a contextual Prepare.

## Behavior by profile and platform

| Profile | Windows | Linux | Effective access priority |
| --- | --- | --- | --- |
| `dedicated` | Prepare rejects any active console session, including a local LABUSER session. The wizard configures `SeDenyInteractiveLogonRight` for existing local accounts, except LABUSER and built-in Windows accounts; therefore, LABUSER can still sign in locally. | Prepare rejects any user session associated with a local seat, including `labuser`. Profile setup does not apply an equivalent restriction on interactive local sign-in. | A remote reservation does not displace a local LABUSER session. A local session for another account also blocks Prepare. The desired rule—remote access takes precedence over LABUSER, but not over other accounts—is not implemented yet. |
| `hybrid` | Allows interactive local sign-in. When `local-mode` is active, Prepare is rejected. If it is off and local sessions exist, Prepare requests graphical confirmation from each eligible session when `AllowLocalSessionEviction` is enabled. | The policy is equivalent: local sessions are detected through `loginctl`; with `local-mode` active, Prepare is rejected, and when eviction is allowed, each eligible session must confirm. | This is a sequential handoff, not guaranteed simultaneous local and remote use. `local-mode` protects declared local use; without it, remote access can request a handoff through the warning and confirmation. |
| `fmu-only` | Not supported as a physical profile for Prepare/Release. | Does not install Tiny Desk and does not support physical Prepare/Release. | Outside this physical-access matrix. |

Windows and Linux classify physical sessions as local and RDP/XRDP sessions as remote, regardless of account. Linux uses the `loginctl` seat; Windows identifies the `console` session. Therefore, a remote session under another account does not set `localSessionActive`.

## Prepare matrix

The profile columns apply to both Windows and Linux unless a platform difference is called out. Both the Gateway and the Station agent fail safely when they cannot verify a required value.

| Condition when preparing | `dedicated` | `hybrid` | Does Prepare continue? |
| --- | --- | --- | --- |
| No local session; `local-mode` off; inventory known | Continues if all other checks pass. | Continues if all other checks pass. | Yes. Prepare cleans the managed environment and FMU Executor state first. |
| Local LABUSER session | Rejects Prepare, just as it does for another local account. | With `AllowLocalSessionEviction=true`, displays a graphical confirmation and waits through the grace period; eviction occurs only after the required confirmation. If eviction is disabled, Prepare is rejected. | Prepare can continue in Hybrid after consent. A decline, timeout, unavailable dialog, or inventory change leaves the session open and cancels cleanup. |
| Local session for another account | Rejects Prepare. | Uses the same confirmation/eviction policy as a local LABUSER session. | On Windows, the wizard normally prevents existing non-exempt accounts from signing in locally under Dedicated; if such a session exists anyway, Prepare rejects it. Linux does not impose that profile-based restriction. |
| `local-mode` active or state unknown | Rejects. Although only Hybrid can enable it, an active or invalid marker also blocks Prepare. | Rejects before showing a warning or evicting sessions. | No. The agent rechecks the state on both profiles and platforms. A malformed marker remains active until explicitly cleared. |
| Session inventory unknown or inconsistent | Rejects. | Rejects; does not attempt to evict sessions it cannot identify. | No. Gateway also requires a known inventory for administrative Prepare. |
| Remote LABUSER session with no active lease | Administrative/manual Prepare detects it and rejects before cleanup. | Same as Dedicated. | **Route difference:** Prepare for a new reservation does not perform this same specific remote-LABUSER check; it relies on lease admission. If an active or recovery lease exists, the new Prepare is blocked. A residual remote session without a lease does not receive that protection on the lease-bound route. |
| Remote session under another account, with no active lease | Not considered a local session and does not trigger the Dedicated block. | Does not trigger the local-session confirmation. | Prepare may continue without closing that session. Cleanup of the shared application and FMU Executor may affect it; this is not a safe multi-session coexistence policy. |
| Lease active, being prepared, or requiring recovery | Administrative Prepare is rejected. | Same as Dedicated. | A new contextual Prepare is allowed only when no other active lease or pending recovery exists. The reservation flow uses identity and generation to prevent overlap. |
| `AllowLocalSessionEviction=false` with a local session | Still rejects due to the profile. | Rejects without showing a warning. | No. This option is enabled by default in new installations, but can be changed in configuration. |

In Hybrid, the warning requires affirmative confirmation; it is not an informational message that permits automatic eviction. The explicit `--no-guard` option skips the warning and grace period and starts immediate eviction when policy allows it. It does not enable `local-mode` or make Dedicated accept local sessions. The normal flow requires confirmation.

### Administrative Prepare versus lease-bound Prepare

| Route | Authorization and guards | Lease outcome |
| --- | --- | --- |
| Administrative/manual | Uses the administrative channel. Requires no active lease. Gateway requires a known profile and inventory, `local-mode` off, and no remote LABUSER session; Station repeats the relevant checks before cleanup. | Does not create a reservation lease or authorize the remote user to connect. This is operational preparation outside an active reservation. |
| Reservation or demo | Requires a valid Dispatcher v2 envelope. Station rejects another active or recovery lease; it applies `local-mode`, the local-session policy, and Hybrid confirmation. | When Prepare is accepted, Station records the lease and its generation. Success or a non-fatal warning may leave it active; incomplete cleanup or an uncertain result may leave it in `recovery-required`. The connection/reservation alone does not create this state. |

The remote LABUSER check is limited to administrative/manual Prepare in the current agents. The lease-bound route checks the inventory but does not specifically reject a remote LABUSER session when there is no prior lease. This is a policy edge case for residual sessions or connections outside the normal lifecycle.

On Windows, the status summary classifies disconnected RDP sessions as inactive, but the manual Prepare check queries LABUSER RDP rows in the session inventory and may still reject them. On Linux, a disconnected XRDP session continues to count while `loginctl` lists it as a remote `labuser` session.

## Release matrix

Both variants have the same session effect; they differ in authorization and which lease state they can modify.

| Variant | Windows | Linux | Lease effect |
| --- | --- | --- | --- |
| Administrative, no active lease | Available through the operator channel if no lease is active. By default, closes only LABUSER RDP sessions. | Available through the operator channel if no lease is active. Closes only `labuser` XRDP/Tiny Desk sessions. | Does not modify a lease. If a lease is active, Station rejects this variant; use that lease's contextual Release. |
| Reservation/demo-bound | Requires the active lease and matching generation. By default, closes LABUSER RDP sessions. | Requires the active lease and matching generation; closes `labuser` XRDP/Tiny Desk sessions. | Gateway builds the context from the recorded Prepare. On success, the lease becomes `released`; if cleanup fails or the result is uncertain, it may become `recovery-required` and block new work until reconciled. |
| Local watchdog on `expiresAt` | Background service runs Release with the expired lease context. | `labstationd` runs Release with the expired lease context. | This is the automatic safeguard for the same lease-bound route, not a third Release type. It does not automatically clear state that requires reconciliation. |

| Sessions present during Release | Result for both Windows and Linux variants |
| --- | --- |
| Physical local console, any account | The local session is not logged off. If FMU Executor cleanup runs, it may interrupt the user's FMU work because the service is shared. |
| Remote LABUSER session | It is closed even if it is residual and there is no longer an active lease; administrative Release can clean up this case. If the session does not exist, it is treated as already released and FMU Executor cleanup is still attempted. |
| Remote session under another account | It is not logged off. Shared FMU Executor cleanup may still interrupt FMU work performed by that session. |
| Session inventory unavailable | Release fails before cleanup completes. On the lease-bound route, state may become `recovery-required`; Gateway must not blindly retry an operation with an uncertain outcome. |

Windows accepts an explicit `--user=<account>` command parameter and can close another account's RDP session if the operator requests it; normal routes use LABUSER. Linux does not accept that parameter for Release and always targets `labuser`.

Release does not reboot the computer by default. If `--reboot` is explicitly requested, the internal check waits for local sessions and the managed remote LABUSER session to end; it does not check all other remote accounts in the same way. Gateway's `power shutdown/hibernate` policy is stricter: it requires local mode off, a complete inventory, and no active user sessions, local or remote.

## Effective priority by active session

| Existing use | Administrative Prepare | Reservation/lease Prepare | Administrative or lease Release |
| --- | --- | --- | --- |
| LABUSER at the local console | Dedicated blocks it. Hybrid blocks it if `local-mode` is active; otherwise, it may request confirmation and evict the session according to policy. | Same profile-based local-session behavior. | Preserves the local session; shared FMU cleanup may affect it. |
| Another account at the local console | Dedicated blocks it. Hybrid applies the same confirmation and eviction rule as for LABUSER. | Same profile-based local-session behavior. | Preserves the local session; shared FMU cleanup may affect it. |
| Remote LABUSER with an active lease | Rejected because a lease is active. | A second Prepare is rejected because the lease already exists. | Administrative Release is rejected. A matching lease Release can close the session and finish the lease. |
| Residual remote LABUSER, no active lease | Rejected by the manual remote-LABUSER check. | The current contextual route does not have the same specific check; it may prepare if it passes the other rules. | Administrative Release can close the session. Contextual Release requires a valid matching lease. |
| Remote session under another account, no active lease | Not classified as local or remote LABUSER; by itself it does not block Prepare. | Does not trigger the local-session policy either. | Remains connected; shared FMU cleanup may interrupt its FMU work. |

## Related controls and limits

- **Local mode:** Can only be enabled in Hybrid, with a known inventory, no active lease, and no remote LABUSER session. Current configurations default to an eight-hour expiration. Enabling it blocks Prepare but not Release; Release does not clear it. Clearing local mode is allowed to remove a stale marker even after the profile changes.
- **Shutdown/hibernate:** Does not use the same session exception as Prepare. Gateway requires the Station to advertise the shutdown guard and blocks the request when `local-mode` is active or unknown, the inventory is unreliable, or any user session is active. Station checks again after the configured delay.
- **`evictable` field:** Must not be used as a substitute for the Prepare decision. The effective decision depends on the profile, `AllowLocalSessionEviction`, `local-mode`, and confirmation. General Windows telemetry may mark local LABUSER as non-evictable while the Prepare-specific guard checks every console session; Linux reports local seat sessions as evictable.
- **Concurrent connections:** Prepare rules do not necessarily block all remote sessions under other accounts. AppControl/FMU cleanup may affect them, so safe coexistence of multiple remote accounts is not guaranteed.
- **Linux support:** The agent README currently declares `supportTier: unverified` and prerelease status; session classification depends on the information provided by `loginctl` and the installed desktop environment.

## Gaps against the Dedicated intent

The stated intent for Dedicated is that remote reservations take precedence over local LABUSER use, but not over another person's local use. Current Prepare behavior does not distinguish those two accounts: both physical sessions block reservations on Windows and Linux. Windows reduces the likelihood of other accounts signing in locally through its account policy, but still allows local LABUSER; Linux applies no equivalent profile-based restriction. The requested priority is therefore not implemented yet.

Hybrid does support turn-based combined use: local mode protects declared on-site use; without that mode, remote access can request a handoff with a warning and confirmation if eviction is enabled. Without `local-mode`, on-site use has no guarantee of indefinite priority.

## Implementation references

- Gateway: `ops-worker/station_action_policy.py`, `ops-worker/station_shutdown_policy.py`, `ops-worker/reservation_operations.py`, `ops-worker/station_lease.py`.
- Windows: `Lab Station/labstation/service/SessionManager.ahk`, `SessionGuard.ahk`, `LeaseDispatcher.ahk`, `diagnostics/Status.ahk`, `system/AccountManager.ahk`, `setup/Wizard.ahk`.
- Linux: `Lab Station Linux/internal/agent/agent.go`, `internal/agent/lease.go`, `internal/host/runtime.go`, `internal/config/config.go`, `contracts/station/gateway-contracts/README.md`.
- Related operational description: `gateway-lab-station-operations.md`.
