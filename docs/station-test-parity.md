# Station Contract v3 test parity

Lab Gateway owns the canonical Station Contract v3 schemas and fixtures under
`contracts/station/v3/`. The portable Windows/Linux scenario matrix is
`docs/station-test-parity.json`; version 2 defines shared expectations and
links every behavior scenario to a native test in each Station repository.

Lab Station and Lab Station Linux vendor the same matrix at
`contracts/station/v3/test-parity.json`, where their AHK and Go suites consume
the portable status, session-safety, cleanup, local-mode, power, recovery,
lease-expiry, and operation-status vectors. When the matrix changes, update
both vendored copies and keep both platform mappings pointing to executable
tests. Native tests retain OS-specific implementation details while asserting
the same policy results.
