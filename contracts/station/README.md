# Station Contract

This directory is the canonical, platform-neutral station contract consumed by
Lab Gateway, Lab Station for Windows, and Lab Station Linux.

- `v2/` freezes representative Windows payloads for the compatibility adapter.
- `v3/` defines the common status/heartbeat, capabilities, and command result
  schemas. Platform-specific details belong under `platformSpecific`.

Consumers must normalize payloads once at ingress. Reservation, readiness,
timeline, AAS, and public status code use the normalized model and must not
inspect Windows paths or transport-specific heartbeat fields.
