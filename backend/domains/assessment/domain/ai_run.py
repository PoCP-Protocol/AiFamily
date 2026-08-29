"""AI Run Ledger domain entity — the record kept for the "AI Run" step in the
migration plan's runtime call chain (section 6):

    Python Business Domain -> Consent & Purpose -> Immutable Context Snapshot
    -> Python AI Runtime -> Skill -> Model Provider -> Schema/Evidence/Safety/Eval
    -> AI Run -> Domain Draft -> family/human confirmation -> Domain Command

Prior to this task, an AI call (`ClaudeInterpretationAdapter.interpret` /
`DeterministicInterpretationAdapter.interpret`) left no trace at all once it
returned — no record that a call happened, which generator handled it, how
long it took, what it cost, or whether it failed boundary validation. This
module defines that trace as a first-class record.

Design reference, not a copy: the NestJS side has no Assessment-domain
equivalent. The closest existing pattern is the Principal module's
provider-attempt ledger (`principal_model_attempts`,
`database/migrations/0014_principal_model_attempts.sql`) — a STARTED row
written before the external call, then updated to SUCCESS/FAILURE with
latency/token/model_name on completion. `AiRunRecord` borrows that shape
(status/model_name/latency/token counters/started_at/finished_at) but is
intentionally NOT a literal port:

- `principal_model_attempts` tracks provider-level attempts (one logical run
  may retry/failover across N providers). This domain's AI Runtime currently
  has exactly one generator per call (deterministic OR live Claude, no
  failover), so `AiRunRecord` is one row per `interpret()` call, not a
  run/attempt two-table split. If Family's Python AI Runtime later adds
  failover across providers, splitting into a run/attempt pair the same way
  `principal_model_runs`/`principal_model_attempts` do would be the natural
  next step.
- This domain's boundary validation (`assert_interpretation_boundary`) is a
  fail-closed content check with no equivalent on the Principal side, so
  `outcome` has a `boundary_violation` value the Principal ledger has no
  need for (Principal's `failure_kind` is provider/transport failures only).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AiRunGenerator = Literal["deterministic", "gateway"]
AiRunOutcome = Literal["success", "boundary_violation", "provider_error"]


class AiRunRecord(BaseModel):
    """One row = one `AssessmentInterpretationPort.interpret()` call, success
    or failure. Written exactly once per call (ledger writers append a single
    completed record rather than a STARTED-then-updated pair, since this
    domain's calls are not long-running/streamed and there is no in-flight
    state worth persisting separately — unlike Principal's attempt ledger,
    which pre-writes STARTED before the external call to survive a crash
    mid-call. If that gap matters here later, add a `record_started`/
    `record_completed` pair to `AiRunLedgerPort` rather than overloading this
    single-record shape.)
    """

    run_id: str
    assessment_session_id: str
    service_depth: str
    generator: AiRunGenerator
    model_name: str | None = None
    started_at: datetime
    completed_at: datetime
    input_tokens: int | None = None
    output_tokens: int | None = None
    outcome: AiRunOutcome
    error_detail: str | None = None
