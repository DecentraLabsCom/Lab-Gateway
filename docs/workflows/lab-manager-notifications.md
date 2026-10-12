# Lab Manager: Notifications

The `Notifications` tab configures email and ICS invitations for reservations
in labs managed by the current Gateway. Each Gateway has its own settings and
recipient list.

## Access and boundaries

- The tab uses the existing Lab Manager session and never requests the
  institution-wide Wallet & Billing administrator token.
- In Full mode, OpenResty forwards the local Lab Manager credential to the
  embedded provider backend. In Lite mode, it forwards the Gateway's mapped
  `LAB_ADMIN_BACKEND_TOKEN` to the configured provider backend and sets the
  Gateway ID itself.
- The provider backend derives an authorization scope from the trusted
  credential and stores settings under that Gateway ID. The browser cannot
  select a different Gateway by changing a request header.
- The backend also applies the configured administrative network policy.

Notifications are available when the provider backend runs in
`provider-consumer` mode. A Lite also needs its trust-bundle entry and remote
Lab Manager backend configured.

The endpoint set is:

```text
GET  /lab-admin/notifications
PUT  /lab-admin/notifications
POST /lab-admin/notifications/test
POST /lab-admin/notifications/send
```

## Tab configuration

`Notifications Setup` can configure:

- `Delivery`: `NOOP`, `SMTP`, or `GRAPH`;
- `From (email)` and `From Name`;
- `Recipients (comma separated)` as default recipients;
- `Timezone` used when creating messages and ICS events; choose `Use Lab
  Gateway timezone` to follow the Gateway/container timezone; and
- `Enabled`.

Driver-specific credentials and parameters are opened through `Configure`.

### NOOP

This is the default driver and sends no email. It is appropriate for
development, backend tests, and deployments where the delivery channel has not
yet been selected. With `NOOP`, the configuration may be enabled but there is
no external delivery.

### SMTP

In `Configure` → `SMTP`, enter:

- `Host` and `Port`, normally `587`;
- `Username` and `Password` when the server requires authentication; and
- `STARTTLS`, enabled unless the mail-server policy says otherwise.

The service validates the host and port and requires a username/password when
`auth=true`. A stored password is not returned to the UI; leaving the field
blank preserves the existing value.

### Microsoft Graph

In `Configure` → `Microsoft Graph`, enter:

- `Tenant ID`;
- `Client ID`;
- `Client Secret`; and
- `From (UPN/mailbox)`.

The service requires all three identifiers and a valid sender, either the Graph
mailbox or `From (email)`. The client secret is not returned; leaving the field
blank preserves the existing value.

## Safe procedure

1. Configure `From`, recipients, and timezone first.
2. Select the driver and complete its driver-specific fields.
3. Enable delivery only after the driver is valid.
4. Click `Save Settings`.
5. Click `Send Test Email` and verify actual delivery, including spam handling
   and ICS data when the reservation flow produces it.
6. If delivery fails, use `Reload Config`, review the driver, and inspect
   `blockchain-services` logs.

The test endpoint rejects the request when no default recipients exist or when
the driver configuration is invalid. `/send` may receive explicit recipients;
when none are provided, it uses `defaultTo`.

## Persistence and secrets

Changes made through the UI are persisted in the file configured by
`NOTIFICATIONS_CONFIG_FILE`. Version 2 stores a separate mail configuration
for each normalized Gateway ID:

```env
NOTIFICATIONS_CONFIG_FILE=./data/notifications-config.json
```

The default is relative to the backend's working directory. Keep the file on
persistent storage, outside Git, with restricted permissions.

Initial values may also come from these backend variables:

```env
NOTIFICATIONS_MAIL_ENABLED=true
NOTIFICATIONS_MAIL_DRIVER=noop
NOTIFICATIONS_MAIL_FROM=
NOTIFICATIONS_MAIL_FROM_NAME=Lab Gateway
NOTIFICATIONS_MAIL_DEFAULT_TO=
# Leave blank to use the Lab Gateway/container timezone.
NOTIFICATIONS_MAIL_TIMEZONE=
NOTIFICATIONS_MAIL_SMTP_HOST=
NOTIFICATIONS_MAIL_SMTP_PORT=587
NOTIFICATIONS_MAIL_SMTP_USERNAME=
NOTIFICATIONS_MAIL_SMTP_PASSWORD=
NOTIFICATIONS_MAIL_SMTP_AUTH=true
NOTIFICATIONS_MAIL_SMTP_STARTTLS=true
NOTIFICATIONS_MAIL_GRAPH_TENANT_ID=
NOTIFICATIONS_MAIL_GRAPH_CLIENT_ID=
NOTIFICATIONS_MAIL_GRAPH_CLIENT_SECRET=
NOTIFICATIONS_MAIL_GRAPH_FROM=
```

The first save of a pre-version-2 global file assigns that configuration only
to the local Full Gateway. A standalone provider backend retains an old global
configuration as unassigned and does not expose it to any Gateway. New remote
Gateway entries start with default settings and do not inherit another
Gateway's credentials.

The GET endpoint returns only public configuration details: it never returns
the SMTP password or Graph client secret, only indicators such as
`passwordConfigured` and `clientSecretConfigured`. Change secrets only
through the protected Lab Manager UI, never in logs, URLs, or documentation.

## Relationship with reservations and Ops Worker

For each reservation event, the provider backend resolves the lab's historical
on-chain `accessURI` at the event block and selects that Gateway's mail
configuration. A lab managed by one Gateway therefore cannot inherit another
Gateway's recipient list or SMTP/Graph credentials.

Ops Worker sends operational failure alerts through the same Gateway-scoped
endpoint. By default, it derives the URL, credential, and token header from
the existing Full local Lab Manager token or Lite backend trust configuration;
it also sends its Gateway ID:

```env
NOTIFICATION_SERVICE_URL=
NOTIFICATION_SERVICE_RECIPIENTS=
NOTIFICATION_SERVICE_RETRY_ATTEMPTS=3
NOTIFICATION_SERVICE_RETRY_BACKOFF_SECONDS=5
```

Notifications do not replace the reservation timeline, on-chain state, or
logs. When an alert fails, diagnose the underlying operation first and then the
delivery path.

## References

- [Wallet and billing](../../blockchain-services/docs/services/wallet/WALLET_BILLING.md)
- [API reference](../../blockchain-services/docs/reference/API_REFERENCE.md)
- [Configuration reference](../reference/configuration.md)
- [Gateway and Lab Station operations](gateway-lab-station-operations.md)
