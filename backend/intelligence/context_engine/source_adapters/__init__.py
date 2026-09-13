"""Pure, read-only transforms from authoritative domain aggregates to
`WorldStateAtom` (AIFAMILY-WM-002).

Every adapter in this package is a function, not a class with its own
persistence — it takes a domain entity plus a caller-supplied `ContextScope`
and returns `WorldStateAtom` instance(s). No adapter here reads a database,
writes a database, or imports a repository: composition (reading the real
domain, then calling the adapter, then appending via
`PostgresWorldStateRepository`) is the caller's job, kept out of this package
so each half stays independently testable.
"""
