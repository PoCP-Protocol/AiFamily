# ADR-0089: Durable Prompt and Schema Registry versions

- Status: Accepted
- Date: 2026-08-30

## Decision

Prompt bundles and output schemas are immutable version assets. In addition to
the deterministic in-memory adapters, AiFamily provides session-bound SQL
adapters and migration `0030_ai_prompt_schema_registry`. A `(ref, version)`
identity cannot be overwritten; lifecycle transitions create a new version and
mark the previous row superseded. Resolution returns exactly one published,
effective version bound to both `use_case` and `agent_id`; missing or ambiguous
assets fail closed.

The adapters persist policy metadata and schema definitions only. They do not
invoke a model, persist family payloads, or write canonical business facts.
Transactions remain owned by the composition root so test, staging and
production can use the same runtime semantics with different database adapters.

## Consequences

- A process restart cannot silently lose the prompt/schema versions used for
  provenance and replay.
- Roll-forward preserves historical versions; accidental in-place edits and
  ambiguous effective bindings are rejected.
- Operator signatures, governance-YAML loading and mandatory composition-root
  resolution remain explicit follow-up work rather than being implied by SQL
  persistence alone.
