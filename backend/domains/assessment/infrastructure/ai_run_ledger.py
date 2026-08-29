"""AI Run Ledger writers — see `domain/ai_run.py` for the record shape and
design rationale, and `database/migrations/0045_ai_run_ledger.sql` for the
table this real implementation writes to.

Fail-open, by design, for THIS ledger's writes specifically: ledger writes
are a diagnostic/audit side-channel on top of an AI Runtime call whose
result has already been computed (success draft or a raised domain error).
A ledger write failure (e.g. a transient DB error) must not turn an
otherwise-successful `interpret()` call into a failure the family-facing
flow sees, and must not swallow/replace a domain error already being raised
for a boundary violation or provider error. This is a narrower, deliberate
exception to this project's general fail-closed posture (`CLAUDE.md` C06
"Audit"/Coding Constitution stop-condition #5 territory is about *changing*
audit/safety semantics, not about a monitoring write failing silently) —
the AI content boundary checks (`assert_interpretation_boundary`,
`is_live_external_ai_authorized`) remain strictly fail-closed and are
completely unaffected by ledger write outcomes. If this project's owner
later decides audit-write failures for AI Runtime calls specifically should
fail-closed (block the response), that is a policy call for a human to make
explicitly — this implementation defaults to "never let a monitoring write
break the user-facing outcome" and logs the failure instead of raising.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.ports import AiRunLedgerPort
from ..domain.ai_run import AiRunRecord

logger = logging.getLogger(__name__)


class SqlAlchemyAiRunLedger(AiRunLedgerPort):
    """Writes one row per `record()` call to `ai_run_ledger`. Uses its own
    connection (not the caller's in-flight request transaction) so a ledger
    write failure — or a rollback of the caller's transaction for an
    unrelated reason — cannot retroactively erase or block the audit trail;
    see module docstring for the fail-open rationale specific to this
    ledger.
    """

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def record(self, run: AiRunRecord) -> None:
        try:
            await self._connection.execute(
                text(
                    """
                    insert into ai_run_ledger(
                        run_id, assessment_session_id, service_depth, generator, model_name,
                        started_at, completed_at, input_tokens, output_tokens, outcome, error_detail
                    ) values (
                        :run_id, :assessment_session_id, :service_depth, :generator, :model_name,
                        :started_at, :completed_at, :input_tokens, :output_tokens, :outcome, :error_detail
                    )
                    """
                ),
                {
                    "run_id": run.run_id,
                    "assessment_session_id": run.assessment_session_id,
                    "service_depth": run.service_depth,
                    "generator": run.generator,
                    "model_name": run.model_name,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "outcome": run.outcome,
                    "error_detail": run.error_detail,
                },
            )
            await self._connection.commit()
        except Exception:  # noqa: BLE001 — deliberate: see module docstring (fail-open for ledger writes only)
            logger.exception("ai_run_ledger_write_failed run_id=%s outcome=%s", run.run_id, run.outcome)
