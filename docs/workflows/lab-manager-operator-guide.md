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
| 4 | `Digital Twins` | Synchronize an FMU with AAS or link an external shell. | `fmu-runner`, Ops Worker, and BaSyx through `/aas-admin/**`. |
| 5 | `Notifications` | Configure and test reservation email/ICS delivery. | `blockchain-services` through `/billing/admin/notifications/**`. |

The tabs are declared in [Lab Manager](../../web/lab-manager/index.html) and
grouped dynamically by [lab-manager-tabs.js](../../web/assets/js/lab-manager-tabs.js).

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
| `labId` | Stable laboratory identity in the contract/provider projection. | Energy policies, AAS overrides, and reservations. |
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

## Recommended order for an FMU and its digital twin

1. Install and validate the FMU on Lab Station; see
   [FMI/FMU support](../fmi-fmu-support.md).
2. Publish it from `Labs` as an `FMU simulation`. The `accessKey` must point
   to the FMU's operational identifier and `accessURI` must be the Gateway's
   public FMU endpoint.
3. Open `Digital Twins` → `FMU Digital Twin Sync`. The `Access Key` selector
   is populated from published FMUs; `Laboratory` is an optional override that
   anchors the identity to a `labId`.
4. Either generate the shell automatically or upload a validated `.aasx` file.
5. If an external shell already exists, use `Link Existing AAS` instead of
   generating another one. The difference and identity rules are described in
   [AAS support](../aas-support.md).
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
