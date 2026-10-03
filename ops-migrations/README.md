# Gateway Ops migrations

These migrations provision the durable local access-plane state used by
`ops-worker` in both Full and Lite deployments.

The `ops-schema-migrator` Compose service runs Flyway before either the
embedded `blockchain-services` process or `ops-worker` starts. This is
important in Lite mode: the embedded Java backend is intentionally dormant,
while the local gateway still owns Guacamole, Lab Station and Ops execution.

The migrations use their own `flyway_ops_schema_history` table. Existing
Gateway databases may already contain some of these tables because older
versions created them through the backend Flyway history or MySQL bootstrap
scripts. `baselineOnMigrate` plus idempotent DDL lets the one-shot migrator
adopt those databases without recreating data.

The remote Full Gateway or standalone `blockchain-services` remains the
control plane for reservations, credentials and blockchain state. Nothing in
this directory attempts to mirror that remote control-plane database.
