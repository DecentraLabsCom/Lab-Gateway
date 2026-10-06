# Station Contract v3 test parity

Lab Gateway owns the canonical Station Contract v3 schemas and fixtures under
`contracts/station/v3/`. The portable Windows/Linux scenario matrix is
`docs/station-test-parity.json`; it lists shared expectations and links each
scenario to a native test.

Lab Station and Lab Station Linux vendor the same matrix at
`contracts/station/v3/test-parity.json`, where their AHK and Go suites consume
the portable status, session-safety, power, and recovery vectors. When the
matrix changes, update both vendored copies and keep both platform mappings
pointing to executable tests. Platform-specific behavior remains in each
station's native test suites.
