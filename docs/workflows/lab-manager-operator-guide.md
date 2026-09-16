# Lab Manager Operator Guide

This is the starting point for operators who manage a laboratory through
`/lab-manager`. The interface is a static web application, but each tab talks
to a different Gateway component or control-plane service. The configuration
order therefore matters.

## What each tab does

| Order | Tab | Main purpose | Processes behind it |
| --- | --- | --- | --- |
| 1 | `Labs` | Publish, edit, and maintain physical laboratories or FMU simulations. | `blockchain-services` through `/lab-admin/**`; local discovery through Ops Worker. |
| 2 | `Operations` | Monitor stations, heartbeat, reservations, and timelines. | Ops Worker through `/ops/**`; cancellation through `/lab-admin/**`. |
| 3 | `Energy` | Manage credentials, controllers, outlets, policies, and power tests. | Ops Worker through `/ops/api/power/**`. |
| 4 | `Digital Twins` | Synchronize an FMU or physical laboratory with AAS, import a prepared AASX, or link an external shell. | `fmu-runner`, Ops Worker, and BaSyx through `/aas-admin/**`. |
| 5 | `Notifications` | Configure and test reservation email/ICS delivery. | `blockchain-services` through `/billing/admin/notifications/**`. |

The tabs are declared in [Lab Manager](../../web/lab-manager/index.html) and
grouped dynamically by [lab-manager-tabs.js](../../web/assets/js/lab-manager-tabs.js).

The shared header and tab bar look like this in a Full Gateway. The active
panel changes which backend surface is queried; the access-policy badge remains
visible so operators can tell whether the dashboard is restricted to localhost
or an allowed private CIDR.

![Lab Manager Laboratories tab](../images/lab-manager-laboratories.png)

## Full, Lite, and permissions

| Capability | Full Gateway | Lite Gateway |
| --- | --- | --- |
| `Labs` | Available when the local backend runs in `provider-consumer` mode. | Available only when `LAB_ADMIN_BACKEND_URL`, `LAB_ADMIN_BACKEND_TOKEN`, and its header are configured. |
| `Operations` | Uses the local Ops Worker and stations. | Uses the Lite Gateway's local Ops Worker and stations. |
| `Energy` | Uses controllers local to the Gateway. | Uses controllers local to the Lite Gateway. |
| `Digital Twins` | Available when AAS/FMUs are configured. | Disabled by the UI and blocked by the backend. |
| `Notifications` | Available through the local administrative backend. | Disabled; configuration belongs to the Full control plane. |

`LAB_MANAGER_TOKEN` protects the Lab Manager session, `/lab-admin`, `/ops`, and
AAS administration routes. `Notifications` is the exception: opening it asks
for the Wallet & Billing administrator token and must not request that token
while the other tabs are loading.

Network policy still applies even when a token is present. `/ops/` and
administrative operations are intended for localhost or explicitly allowed
private networks. In Lite mode, the browser may display the interface, but
remote routes must be explicitly configured and authorized.

## Identifiers that must not be confused

| Identifier | Meaning | Where it is used |
| --- | --- | --- |
| `labId` | Stable laboratory identity in the contract/provider projection. | Energy policies, AAS synchronization/linking, and reservations. |
| `accessKey` | Operational reference for the published resource. | `guac:id:<connection_id>` for physical labs; FMU filename/reference for FMUs. |
| `reservationKey` | On-chain reservation identifier. | Cancellation, timeline, and session diagnosis. |
| `controllerId` | Local identifier for an energy controller. | JSON catalog and policies. |
| `credentialRef` | Local reference to an encrypted credential. | APC, SNMP, and NETIO controllers. It is never the secret. |

## Recommended order for a physical laboratory

1. Deploy the Gateway and verify [configuration](../reference/configuration.md)
   and [health](../reference/operations-and-health.md).
2. Create and test the local Guacamole connection using
   [Guacamole connections](../configuring-lab-connections/guacamole-connections.md).
3. Prepare Lab Station, Wake-on-LAN, WinRM, and heartbeat according to
   [Gateway and Lab Station operations](gateway-lab-station-operations.md).
4. Open `Labs`, publish the laboratory, and confirm that the `labId` and
   `accessKey` are the expected values.
5. Configure `Energy` if a smart power strip is present. Never cut power to
   the Gateway, network switch, or any control-plane equipment with that strip.
6. Return to `Operations`, provision the host, save WinRM credentials, check
   heartbeat, and run a controlled test.
7. Create a test reservation and inspect the complete timeline: WoL,
   `prepare-session`, access, `release-session`, and any power actions.

The details for steps 3, 4, and 6 are in [Labs and Operations](lab-manager-labs-and-operations.md).
The complete energy workflow is in [Lab Manager energy operations](lab-manager-energy-operations.md).

## Recommended order for an FMU or physical laboratory digital twin

1. For an FMU, install and validate the model on Lab Station; see
   [FMI/FMU support](../fmi-fmu-support.md). For local execution tests, start
   `fmu-local-dev` together with `aas`:
   `docker compose --profile fmu-local-dev --profile aas up -d`. Do not run
   `fmu-runner` at the same time because both profiles use the `fmu-runner`
   proxy alias. For a physical lab, first complete the normal `Labs`,
   `Operations`, and Lab Station setup.
2. Publish the resource from `Labs` and confirm its stable `labId`. FMUs retain
   their operational `accessKey`; physical labs retain their Guacamole
   `accessKey`, but neither is selected manually in Digital Twins.
3. Open `Digital Twins` → `Digital Twin Management` and select the
   laboratory. The selector includes FMUs and physical laboratories and uses
   the `labId` to associate the operation automatically.
4. Click `Sync AAS` to generate metadata. FMUs use the model description when
   available, otherwise the registered laboratory description. Physical labs
   use Gateway/heartbeat data plus the registered description, documentation,
   and Terms of Use. No separate Documentation or License fields are required.
5. Optionally upload a provider-prepared `.aasx`. The package must contain
   `urn:decentralabs:lab:{labId}` as a shell ID, unless the shell is associated
   through `Link Existing AAS`. Use that panel when the authoritative shell is
   already hosted elsewhere.
6. Verify shell retrieval through the Gateway, not only directly against BaSyx.

## Notification workflow

1. Open `Notifications` only when changing or testing the configuration.
2. Enter the Wallet & Billing administrator token when prompted.
3. Choose `NOOP`, `SMTP`, or `GRAPH`, complete the form, and save.
4. Use `Send Test Email` and verify recipients, logs, and ICS calendar data
   when applicable.

The detailed configuration, secrets, and persistence rules are in
[Notifications](lab-manager-notifications.md).

## First-level diagnosis

| Symptom | First check |
| --- | --- |
| No laboratory appears in selectors | Refresh `Labs`, verify `LAB_MANAGER_TOKEN`, and check the publication backend. |
| `Operations` shows a network warning | Access from localhost or an allowed CIDR; check dashboard policy. |
| `Digital Twins` or `Notifications` are disabled | Confirm that the Gateway is Full and is not running with an external `ISSUER`. |
| A tab loads but its data is empty | Identify the responsible route in the opening table and inspect that service, not only the browser. |
| The timeline has no events | Use the correct on-chain `reservationKey` and check heartbeat, Ops Worker, and MySQL. |

## Reference documentation

- [Labs and Operations](lab-manager-labs-and-operations.md)
- [Energy](lab-manager-energy-operations.md)
- [Notifications](lab-manager-notifications.md)
- [Deployment architectures](../deployment-architectures.md)
- [AAS support](../aas-support.md)
- [FMI/FMU support](../fmi-fmu-support.md)
- [Guacamole session policy](../guacamole-session-policy.md)
