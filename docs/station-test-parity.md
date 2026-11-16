# Station Contract v3 test parity

Lab Gateway owns the canonical Station Contract v3 schemas and fixtures under
`contracts/station/v3/`. The portable Windows/Linux scenario matrix is
`docs/station-test-parity.json`; version 3 defines shared expectations and
links every behavior scenario to a native test in each Station repository.

Lab Station and Lab Station Linux vendor the same matrix at
`contracts/station/v3/test-parity.json`, where their AHK and Go suites consume
the portable status, session-safety, cleanup, local-mode, power, recovery,
lease-expiry, and operation-status vectors. When the matrix changes, update
both vendored copies and keep both platform mappings pointing to executable
tests. Native tests retain OS-specific implementation details while asserting
the same policy results.

For Prepare, Dedicated warns every active user session, waits through the
grace period, then logs it off without a confirmation prompt. Hybrid requires
local mode to be off and, when eviction is enabled, requires each affected
local user to acknowledge the warning before the grace period and logoff.
