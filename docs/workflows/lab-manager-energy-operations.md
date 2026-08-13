# Laboratory Energy Operations from Lab Manager

This guide describes the implemented workflow for registering power
controllers, storing their credentials, defining outlets, and associating them
with laboratory energy policies. Control names remain in English because they
are the labels currently shown in Lab Manager.

## What is configured and where it is stored

| Element | Lab Manager section | Current persistence |
| --- | --- | --- |
| APC/SNMP/NETIO credentials | `Energy Credentials` | Encrypted local JSON store at `OPS_POWER_CREDENTIALS_PATH`. Only references and types are returned. |
| Controllers and outlets | `Power Controllers` | Local JSON catalog at `OPS_POWER_CONFIG`. |
| Laboratory policies | `Lab Power Control` → `Lab power policy` | The same local JSON catalog. |
| Operation results and idempotency | `Lab Power Control`, timeline, and Ops APIs | MySQL, primarily `power_operations`; migration `mysql/003-energy-policies.sql`. |
| WoL, WinRM, and station shutdown | `Lab Station Ops` | Ops Worker, Lab Station, and their operational records; these are not PDU controllers. |

In the MVP, `controllers`, `outlets`, and `policies` remain JSON-backed. The
MySQL table does not replace that catalog: it keeps operation detail and
idempotency for executed actions.

## Before starting

1. Publish the laboratory in the `Labs` tab, under `Publish remote labs and
   FMU simulations from this Gateway`. The policy's `Laboratory` selector is
   populated from those laboratories; do not type the visible name manually.
2. Confirm that Ops Worker is enabled and that the Gateway can reach the
   controller's private network. The controller must not be powered through
   the strip that it is expected to switch off.
3. Configure a stable `OPS_SECRETS_KEY` and the usual paths:

   ```env
   OPS_POWER_CONFIG=/app/data/power-controllers.json
   OPS_POWER_CREDENTIALS_PATH=/app/data/power-credentials.json
   ```

   In Compose, `/app/data` maps to the `ops-data` volume. These files must not
   be committed to Git or included in an unprotected backup.
4. On existing deployments, apply `mysql/003-energy-policies.sql` before
   enabling physical power control. Without the migration, the worker may fall
   back to process-local idempotency and durable operation history will be
   incomplete.
5. Verify WoL, WinRM, and the Lab Station heartbeat separately using
   [Gateway and Lab Station operations](gateway-lab-station-operations.md).

Energy control uses the Lab Manager token (`LAB_MANAGER_TOKEN`). It does not
require the Wallet/Admin token requested by `Notifications`. In Lite mode, the
remote backend remains the control-plane authority, while controllers, Ops
Worker, and the laboratory network remain local to the Lite Gateway.

## Recommended procedure

### 1. Register the device credential

In `Energy` → `Energy Credentials`:

1. Leave `Existing credential` set to `New credential`.
2. Enter a stable `Credential reference`, for example `pdu-lab-01-snmp`. It
   must start with a lowercase letter or number and use only lowercase
   letters, numbers, `.`, `_`, `:`, or `-`.
3. Select the type matching the driver:

   | Type | Use |
   | --- | --- |
   | `NETIO HTTP Basic` | NETIO HTTP(S) API username and password. |
   | `SNMP v1` / `SNMP v2c` | SNMP community and matching version. |
   | `SNMP v3` | Username, authentication, privacy, and optional `context name`. |

4. Click `Save Credential`.

The reference may appear in the catalog and UI; communities, passwords, and
tokens must not. The API returns metadata only. Selecting an existing
reference starts a rotation: enter the replacement secret and click
`Save Credential` again. The controller keeps the same reference and the
runtime is reloaded when possible.

### 2. Register the controller and outlets

In `Energy` → `Power Controllers`, select `New controller` and complete:

- `Controller ID`: stable identifier used by policies, for example `pdu-lab-01`;
- `Name`: operator-friendly name;
- `Driver`: `APC PowerNet SNMP`, `NETIO REST JSON`, or `Mock (development)`;
- `Enabled`, `Host / IP address`, `Port`, and `Credential reference`; and
- `Timeout (seconds)` and `Retries` appropriate for the private network.

For APC:

- normally use SNMP port `161`;
- select `APC profile`: `Auto-detect`, `Legacy PowerNet`, or `rPDU2`;
- set `SNMP version` when the driver default should not be used; and
- use an SNMP credential matching that version.

For NETIO:

- use `NETIO REST JSON` and the device's HTTP/HTTPS port;
- keep `NETIO API path` at `/netio.json` unless the firmware requires another
  path;
- enable `Use HTTPS` and keep `Verify TLS certificate` enabled when the
  certificate can be verified; and
- use a `NETIO HTTP Basic` credential.

Then, under `Outlets`, click `Add outlet` for every socket that a policy may
switch. Define:

- the device's real outlet identifier (`outlet`);
- `Display name` and `Logical name` for operator recognition;
- `Default state`, normally `Off`;
- `Critical` for equipment required to start or close the laboratory; and
- `Protected` for outlets that must not be switched accidentally.

Outlet identifiers must be unique within the controller. Click `Save
Controller`. The catalog is written to `OPS_POWER_CONFIG` and the worker
reloads its runtime. If the physical controller is unavailable during reload,
the configuration may still persist, but actions will fail until connectivity
or credentials are fixed.

### 3. Create the laboratory policy

In `Energy` → `Lab Power Control` → `Lab power policy`:

1. Leave `Existing policy` set to `New policy`.
2. Select the laboratory in `Laboratory`. This selector lists laboratories
   published in `Labs`.
3. Set `Policy name` and enable `Enabled`.
4. Keep `Respect local mode` enabled unless a controlled maintenance
   procedure explicitly requires otherwise. This prevents remote automation
   from interfering with local station operation.
5. Use `Maintenance mode` only for a controlled maintenance policy.
6. As a starting point, use `Fail reservation start` for critical startup
   actions and `Warn and continue` for reservation-end cleanup when a failed
   shutdown should not block the rest of the flow.
7. Click `Add step` and define the actions.

Each step contains at least `Phase`, `Sequence`, `Controller`, `Outlet`, and
`Action`. Actions are `on`, `off`, and `cycle`. You can also set `Desired
state`, cycle timing, delays, timeout, retries, and `Required`, `Read back
state`, and `Allow protected outlet`. `Conditions` is optional advanced JSON;
it must contain a valid JSON object.

Available phases are:

| Phase | Typical use |
| --- | --- |
| `pre_start` | Power PLCs, HMIs, and other equipment before waking/preparing the station. |
| `start` / `post_start` | Actions during or after preparation. |
| `pre_end` | Prepare shutdown before releasing the reservation. |
| `end` / `post_end` | Turn off non-critical and then critical outlets. |
| `manual`, `maintenance`, `emergency_stop` | Explicit procedures outside the normal cycle. |

`Sequence` must be unique within each phase. A typical initial policy powers
critical outlets on in `pre_start` and powers them off in reverse order in
`post_end`. Do not include the strip itself, the network switch, the Gateway,
the Guacamole host, or any equipment required to keep laboratory control and
connectivity alive.

Click `Save Policy`. The policy is associated with the selected `labId`, not
the visible laboratory name. Renaming the lab must not create a second policy.

### 4. Run a controlled test

Start with a non-critical outlet and a clear `Operation reason`.

1. In `Lab Power Control`, confirm that the controller appears, its outlets
   have the expected names, and their state is not `unknown`.
2. Run `On`, wait for the equipment to start, and verify the read-back state.
3. Run `Off` only when the equipment tolerates that test.
4. Use `Cycle` only when `Cycle off time` is safe for the equipment.
5. For a `Protected` outlet, enable `Maintenance mode` first. The UI and API
   reject the action without that explicit override.
6. Review the operation in the history and reservation timeline.

To test a policy without switching hardware, use the protected Ops endpoint
with `dryRun`:

```http
POST /ops/api/labs/<labId>/power/start
Content-Type: application/json

{"reservationId":"energy-dry-run-001","actor":"lab-manager","dryRun":true}
```

The equivalent closing phase is `POST /ops/api/labs/<labId>/power/end`.
Review operations for a reservation with:

```http
GET /ops/api/power/operations?reservationId=energy-dry-run-001
```

The `Mock (development)` driver is intended for development and CI. Its state
can be reset with `POST /ops/api/power/mock/reset`; this does not validate
physical-device connectivity.

## Integration with reservations, WoL, and Lab Station

When `OPS_RESERVATION_AUTOMATION=true` and an enabled policy exists, the normal
flow is:

| Moment | Operation |
| --- | --- |
| Before start | Policy `pre_start` phase. |
| Preparation | WoL and Lab Station `prepare-session`; `start`/`post_start` phases run according to the scheduler. |
| Before end | Policy `pre_end` phase, when defined. |
| Release | `release-session` and the configured closing operation. |
| After end | Policy `post_end` phase, normally to switch outlets off. |

Energy automation does not replace WoL, WinRM, heartbeat, or Lab Station
session control. These are complementary layers. `respectLocalMode` prevents
the policy from being applied when the heartbeat reports local station
operation, according to the implemented flow.

## Credential rotation and maintenance

To rotate an APC, NETIO, or other compatible controller credential:

1. Open `Energy` → `Energy Credentials`.
2. Select the existing reference.
3. Enter the replacement secret, keeping the correct type.
4. Save it and perform a state read or non-critical manual test.

There is no need to edit `power-controllers.json`: `credentialRef` does not
change. The UI never loads the old secret into the browser and the API never
returns it.

Rotating the master `OPS_SECRETS_KEY` is different from rotating a device
password. Perform it in a maintenance window and keep a protected copy of the
new key and encrypted store together. The existing `rotate_secrets.py` script
documented in `ops-worker/README.md` validates the WinRM credential-store
format; do not run it blindly against an energy store containing SNMP entries.
For the MVP, Lab Manager covers device-secret rotation, which is the normal
operation.

## Quick diagnosis

| Symptom | Checks |
| --- | --- |
| `Laboratory` does not show the lab | Publish it in `Labs`, verify the Lab Manager session, and reload the list. |
| No credentials appear | Check `OPS_POWER_CREDENTIALS_PATH`, `OPS_SECRETS_KEY`, volume permissions, and Ops Worker logs. |
| Controller appears but is `unknown` | Check host/IP, port, private route, driver, profile/version, and credential reference. |
| An outlet is missing from the policy | Save it inside the controller and use the device's actual outlet identifier. |
| A protected outlet is rejected | Enable `Maintenance mode` for an authorized test; do not unprotect it merely to bypass the control. |
| Policy saves but does not run | Check `Enabled`, `labId`, migration `003`, reservation automation, and `Respect local mode`. |
| A required action aborts startup | Check connectivity, read-back, timeout/retries, and `Start failure mode`. |
| Durable history is missing | Confirm that `power_operations` exists and the worker can reach Gateway MySQL. |
| Lab Manager works remotely but Ops does not | `/ops/` is restricted to loopback and RFC1918 networks; use the Gateway or private network. |

## Related references

- [Ops Worker README](../../ops-worker/README.md): variables, drivers, stores, and security boundaries.
- [Gateway and Lab Station operations](gateway-lab-station-operations.md): WoL, WinRM, heartbeat, reservations, and timeline.
- [Laboratory connectivity](laboratory-connectivity.md): private-network topology and segmentation.
- [Lab Station WoL and energy playbook](../../../Lab Station/docs/bios-wol-playbook.md): BIOS, NIC, WoL, and station diagnostics.
- [`power-controllers.sample.json`](../../ops-worker/power-controllers.sample.json): sample JSON structure.
- [`003-energy-policies.sql`](../../mysql/003-energy-policies.sql): durable history and idempotency.
