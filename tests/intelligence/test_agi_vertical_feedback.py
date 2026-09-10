import pytest

from backend.intelligence.agi_vertical_feedback import LedgerFeedbackPort
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunScope,
)


@pytest.mark.asyncio
async def test_ledger_feedback_port_is_need_and_scope_bound() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant", "family", ("child",))
    ledger.create_draft(
        scope=scope,
        run_id="run-1",
        request_ref="request-1",
        draft_payload={"family_need_id": "need-1", "path_id": "path-1"},
        idempotency_key="create-1",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-1",
        interaction_type=InteractionType.FEEDBACK,
        payload={"signal": "helpful", "feedback_ref": "feedback-1"},
        idempotency_key="feedback-1",
    )

    port = LedgerFeedbackPort(ledger, lambda _: scope)

    assert await port.latest(family_need_id="need-1") == ("feedback-1",)
    assert await port.latest(family_need_id="need-other") == ()
