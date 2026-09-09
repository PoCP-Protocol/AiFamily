# AGI Vertical Evaluation Spec — Family Understanding MVP

Status: QA specification, not a product capability claim.

This document defines the minimum evidence required to say that a family
understanding vertical slice is useful, traceable, durable, and recoverable.
The evaluation is run against one exact integration ref. Evidence from another
ref, a fake adapter, an in-memory store, SQLite, skipped tests, or a page that
was not exercised by an authenticated browser is non-passing.

## Canonical user scenario

```text
guardian signs in
→ expresses one concrete family difficulty
→ system records bounded evidence
→ system returns an explanation draft with observations, contradictions,
  unknowns, evidence references, and explicit non-fact boundary
→ guardian edits or rejects the understanding
→ system produces a changed, explainable path draft
→ guardian refreshes and a new process reads the same durable version
→ a second family receives a different result from different durable evidence
→ failure/retry/replay/deletion/cross-scope paths remain safe and recoverable
```

## Scenario matrix

| ID | User-visible question | Required real evidence | Passing assertion |
|---|---|---|---|
| V-01 | Did the system understand the first expression? | HTTP request, persisted source/evidence rows, browser projection | Explanation cites the submitted evidence and labels itself as draft/perspective, not fact or diagnosis. |
| V-02 | Can five dimensions be explained honestly? | Five dimension observations, source refs, contradiction and unknown fields | Each dimension has evidence or an explicit unknown; contradictions are not silently collapsed. |
| V-03 | Does guardian correction matter? | Before/after HTTP bodies, correction row/event, durable lineage | Rejection/edit changes the next draft's focus, reasons, or questions; unchanged output is FAIL. |
| V-04 | Does the same FamilyNeed remain stable? | Need id, context snapshot/version, SQL rows, refresh response | Same confirmed need and unchanged context return the same durable draft version. |
| V-05 | Does restart preserve understanding? | Process-A log, process-B log, SQL before/after, browser readback | New process returns the same persisted draft/version; deterministic recomputation alone is insufficient. |
| V-06 | Are two families genuinely different? | Two family scopes, distinct durable source rows, two HTTP/browser responses | Difference is attributable to stored evidence/context, not family-id branching or fixtures. |
| V-07 | Are provenance and knowledge visible? | Published knowledge id/version, gateway route, model/prompt/schema refs | Every generated claim has a traversable evidence/provenance chain; missing chain fails closed. |
| V-08 | Can the family recover from failure? | Provider timeout/schema failure, retry, idempotency receipt, browser error/retry | Failure is user-safe and retryable; no fabricated success or partial canonical mutation. |
| V-09 | Do negative paths protect families? | Missing/revoked consent, wrong Guardian, cross-family/tenant, deletion, replay | Correct refusal, no object-existence leak, no cross-scope data, no duplicate side effect. |
| V-10 | Is the result counterfactually meaningful? | Controlled change to one evidence/feedback input, same other inputs | Only the changed input's dependent output changes; unrelated output stays stable or explains why it changed. |

## Quality metrics

Metrics are evaluated from captured HTTP/SQL/browser artifacts, never from
implementation intent.

| Metric | Formula / rule | MVP gate |
|---|---|---:|
| Evidence coverage | cited observation inputs / displayed observations | 100% or explicit `UNKNOWN` |
| Contradiction honesty | contradictions displayed / contradictions seeded | 100% |
| Unknown honesty | unknowns displayed / deliberately missing evidence cases | 100% |
| Revision sensitivity | changed output cases / valid guardian corrections | 100% |
| Durable replay | same persisted version after restart / restart cases | 100% |
| Family isolation | cross-scope cases with zero disclosure / cross-scope cases | 100% |
| Provenance completeness | drafts with all required provenance refs / drafts shown | 100% |
| Failure recovery | retryable failures recovered without forbidden mutation / injected failures | 100% |
| Counterfactual locality | unrelated output preserved or explained / counterfactual cases | 100% |

One failed hard-gate case blocks the vertical slice. An aggregate average cannot
hide a missing safety, durability, provenance, or isolation proof.

## Required provenance chain

```text
browser interaction
→ request/correlation/idempotency ref
→ family/tenant/subject scope
→ persisted evidence or feedback row
→ context snapshot/version
→ published Knowledge claim/version (if used)
→ ModelGateway route/attempt/provenance (if AI is used)
→ draft id/version/status
→ guardian decision or rejection
→ audit/outbox/deletion receipt
```

The chain must be queryable after process restart. A string that merely looks
like a provenance id is not evidence.

## Guardian state matrix

Every scenario that reads or mutates child/family understanding must exercise:

1. active Guardian + active consent: allowed;
2. missing authentication or Guardian membership: refused;
3. revoked/expired Guardian or consent: refused and no stale projection;
4. valid Guardian for another family/tenant: refused without existence leak.

## Browser proof

For the golden path, capture URL/title, meaningful DOM snapshot, screenshot,
console warnings/errors, and the visible state transition after each key action.
The browser must use the same exact ref and backend as the HTTP/PG run. A Vite
page load, static screenshot, or component test is not browser acceptance.

## Verdict

`PASS` requires V-01 through V-10 hard-gate evidence. If the composition root,
real HTTP, fresh PostgreSQL, or browser path is unavailable, the verdict is
`BLOCKED`, not partial PASS. If the path runs but violates a required assertion,
the verdict is `FAIL` with the first reproducible failure recorded.
