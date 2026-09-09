# Work Package F — Unified Red-Team Acceptance Matrix

## Scope

This is the QA gate for the A–E candidate at:
`72eec31d178e14a32aa6a05b4189c8c515119975`.

The matrix deliberately treats later or separate candidate refs as out of
scope. Evidence from another ref cannot satisfy this gate.

## Hard gates

### Current MVP P0 blocker

`HEAD=cb7bb5ae92018b75ece502b1dada27a824c76268` fails the first real
business HTTP request under default `create_app()` with
`500 {"detail":"get_family_context_not_wired"}`. Candidate A/D refs are not
both present in this HEAD, so no mixed-ref acceptance is valid. This blocker
must be re-run only after the two refs are composed into one exact candidate.

| ID | Gate | Required proof | Current disposition |
|---|---|---|---|
| F-01 | Default `create_app` | Clean start with default composition root and real HTTP | NOT_RUN |
| F-02 | Fresh PostgreSQL | New database, candidate migrations, SQL row evidence | NOT_RUN |
| F-03 | Restart readback | Stop process A, start process B, same durable record/version | NOT_RUN |
| F-04 | Browser golden path | Authenticated UI interaction, screenshot, DOM and console evidence | NOT_RUN |
| F-05 | Two-family difference | Durable distinct inputs and explainable distinct outputs | NOT_RUN |
| F-06 | Guardian four states | allowed/missing/revoked-or-expired/wrong-scope over HTTP | NOT_RUN |
| F-07 | Published Knowledge + ModelGateway provenance | published version, gateway route and response lineage | NOT_RUN |
| F-08 | Replay/deletion/cross-scope | safe replay, deletion proof, no cross-family/tenant leakage | NOT_RUN |

## Non-passing evidence

The following can support diagnosis but cannot close a gate:

- local unit or component tests only;
- fake, in-memory, SQLite, or dependency-overridden composition;
- skipped PostgreSQL tests;
- documentation, ADRs, route registration, or page existence;
- same-process refresh or deterministic recomputation;
- a screenshot without an exercised authenticated flow;
- a response containing provenance-shaped strings without durable source rows;
- evidence collected from a different commit, branch, or worktree.

## Execution order

1. Freeze and record the approved ref and clean worktree.
2. Create a fresh PostgreSQL database and apply only that ref's migrations.
3. Start the default application composition with no dependency overrides.
4. Run the real HTTP seed and golden-path actions for two families.
5. Capture SQL rows, HTTP bodies, browser DOM/screenshots, and provenance refs.
6. Stop and restart the application; repeat readback requests.
7. Run Guardian, replay, deletion, provider-failure, and cross-scope negatives.
8. Mark each row only from the evidence template; missing proof is not PASS.
