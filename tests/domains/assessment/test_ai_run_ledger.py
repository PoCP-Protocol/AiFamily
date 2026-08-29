"""Unit tests for the AI Run Ledger — verifies the deterministic
interpretation adapter writes an `AiRunRecord` for every outcome, using
`FakeAiRunLedger` (no DB). See `domain/ai_run.py` and
`AI_RUN_LEDGER_NOTES.md` for design rationale.

The equivalent Claude-adapter ledger tests (success / boundary_violation /
provider_error / refusal outcomes) from the source repository are NOT
migrated here: `ClaudeInterpretationAdapter` itself is excluded from this
migration (`import anthropic` violates R7 — no direct model provider calls
outside `backend/intelligence/model_gateway`, which does not exist yet).
See `governance/MIGRATION_MANIFEST.yaml` → `assessment_ai_interpretation_adapter`
(status: BLOCKED) — those tests should be re-added once that adapter is
rewritten against the Model Gateway.
"""

from __future__ import annotations

from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.fake_ai_run_ledger import FakeAiRunLedger


def _evidence() -> GrowthHypothesisEvidence:
    return GrowthHypothesisEvidence(
        assessment_session_id="sess-1",
        subject_person_id="child-1",
        subject_display_name="小明",
        submitted_at=None,
        tool_ref="FAMILY_SUPPORT_NEEDS",
        tool_version=1,
        assessment_response_id="resp-1",
        focus_ref="COMMUNICATION",
        assessment_evidence_id="ev-1",
        need_type_ref="PARENT_CHILD_COMMUNICATION_CONFLICT",
        need_type_version=1,
        title="亲子沟通支持",
        description="先从倾听开始",
        required_capability_keys=["CAP_PARENT_COACHING"],
        response_set=[
            {
                "item_ref": "FOCUS",
                "response_type": "SINGLE_CHOICE",
                "response_value": "COMMUNICATION",
            }
        ],
    )


class TestDeterministicAdapterLedger:
    async def test_fallback_path_still_leaves_an_audit_trail(self):
        """Even with zero external calls, the ledger must record that this
        session's draft came from the deterministic fallback, not a live
        model — the whole point of migration plan §9's AI Run Ledger item.
        """
        ledger = FakeAiRunLedger()
        adapter = DeterministicInterpretationAdapter(ai_run_ledger=ledger)

        await adapter.interpret("family-1", _evidence())

        assert len(ledger.records) == 1
        record = ledger.records[0]
        assert record.generator == "deterministic"
        assert record.model_name is None
        assert record.outcome == "success"
        assert record.assessment_session_id == "sess-1"
        assert record.completed_at >= record.started_at

    async def test_ledger_is_optional_and_backward_compatible(self):
        """Existing call sites that construct with no ledger must keep working."""
        adapter = DeterministicInterpretationAdapter()
        result = await adapter.interpret("family-1", _evidence())
        assert (
            result["interpretation"]["generator"] == "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC"
        )
