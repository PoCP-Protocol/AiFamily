# Context Engine

The Family Context implementation is a pure retrieval primitive. The
`ContextBroker` keeps deterministic in-memory behavior for dev/test, while
`AsyncSqlContextBroker` provides the durable production adapter and
`SqlContextBrokerFactory` is the composition-root seam. Both build
tenant/family/subject/purpose/consent-scoped snapshots with bounded TTL and
never import domain repositories or mutate canonical business state.

Production deployments apply migration `0036_ai_context_engine` before wiring
`install_sql_experience_runtime_wiring(..., context_broker_factory=...)`.
The SQL adapter opens one short-lived session per operation, so snapshots can
be replayed after a process restart without sharing request connections.
