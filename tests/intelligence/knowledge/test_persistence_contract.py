from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.knowledge.contracts import KnowledgeSource
from backend.intelligence.knowledge.persistence import (
    KnowledgeLifecycleEvent,
    KnowledgeSelectionCommand,
    KnowledgeSelectionReceipt,
    PersistedKnowledgeClaimVersion,
    advance_lifecycle,
    content_digest,
    create_selection_receipt,
    validate_replacement_chain,
)
from backend.packages.contracts.evidence import Provenance

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def claim(version="1", **changes):
    text = changes.pop("text", "活动转换可能影响任务开始。")
    values = dict(
        claim_id="knowledge:transition",
        version=version,
        content_digest=content_digest(text),
        text=text,
        source_id="source:reviewed",
        provenance=Provenance(level="E6", source_ref="source:reviewed"),
        scope="family_growth",
        allowed_purposes=("family_problem_understanding",),
        applicability="家庭学习任务开始",
        limitations=("不能据一次表达判断",),
    )
    values.update(changes)
    return PersistedKnowledgeClaimVersion(**values)


def source(**changes):
    values = dict(
        source_id="source:reviewed",
        title="Reviewed",
        license_ref="license:1",
        owner="knowledge",
        scope="shared",
        verified=True,
        status="ACTIVE",
    )
    values.update(changes)
    return KnowledgeSource(**values)


def command(**changes):
    values = dict(
        selection_id="selection:1",
        request_ref="request:1",
        request_fingerprint=content_digest("request"),
        policy_version="knowledge-selection.v1",
        purpose="family_problem_understanding",
        scope="family_growth",
        selected_at=NOW,
        minimum_evidence="E5",
    )
    values.update(changes)
    return KnowledgeSelectionCommand(**values)


def published():
    event = KnowledgeLifecycleEvent(
        "e1", "knowledge:transition", "1", 1, None, "INGESTED", NOW, "actor", "1"
    )
    state = advance_lifecycle(None, event)
    state = replace(state, scope="family_growth")
    for sequence, status in enumerate(
        ("PARSED", "CHUNKED", "GROUNDED", "REVIEWED", "PUBLISHED"), 2
    ):
        state = advance_lifecycle(
            state,
            KnowledgeLifecycleEvent(
                f"e{sequence}",
                state.claim_id,
                state.version,
                sequence,
                state.status,
                status,
                NOW,
                "actor",
                "1",
            ),
        )
    return state


def test_lifecycle_rejects_jump_revival_and_wrong_sequence() -> None:
    with pytest.raises(ValueError, match="transition"):
        advance_lifecycle(
            None, KnowledgeLifecycleEvent("e", "c", "1", 1, None, "PUBLISHED", NOW, "a", "1")
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": ""},
        {"claim_id": ""},
        {"actor_ref": ""},
    ],
)
def test_lifecycle_event_rejects_empty_identity_refs(changes) -> None:
    values = dict(
        event_id="event:1",
        claim_id="knowledge:transition",
        version="1",
        sequence=1,
        previous_status=None,
        status="INGESTED",
        occurred_at=NOW,
        actor_ref="actor:owner",
        expected_version="1",
    )
    values.update(changes)
    with pytest.raises(ValueError, match="references"):
        KnowledgeLifecycleEvent(**values)
    retired = advance_lifecycle(
        published(),
        KnowledgeLifecycleEvent(
            "r", "knowledge:transition", "1", 7, "PUBLISHED", "RETIRED", NOW, "a", "1"
        ),
    )
    with pytest.raises(ValueError, match="transition"):
        advance_lifecycle(
            retired,
            KnowledgeLifecycleEvent(
                "x", retired.claim_id, "1", 8, "RETIRED", "PUBLISHED", NOW, "a", "1"
            ),
        )
    with pytest.raises(ValueError, match="sequence"):
        advance_lifecycle(
            published(),
            KnowledgeLifecycleEvent(
                "x", "knowledge:transition", "1", 9, "PUBLISHED", "RETIRED", NOW, "a", "1"
            ),
        )


def test_replacement_requires_format_existence_scope_and_no_cycle() -> None:
    with pytest.raises(ValueError, match="claim_id@version"):
        claim(replacement_ref="bad ref")
    first = claim(replacement_ref="knowledge:transition@2")
    second = claim("2", replacement_ref="knowledge:transition@1")
    with pytest.raises(ValueError, match="cycle"):
        validate_replacement_chain(first, {first.ref: first, second.ref: second})
    with pytest.raises(ValueError, match="same scope"):
        validate_replacement_chain(first, {second.ref: replace(second, scope="other")})
    chain = {
        f"knowledge:transition@{index}": claim(
            str(index),
            replacement_ref=(f"knowledge:transition@{index + 1}" if index < 10 else None),
        )
        for index in range(1, 11)
    }
    with pytest.raises(ValueError, match="maximum depth"):
        validate_replacement_chain(chain["knowledge:transition@1"], chain, max_depth=8)


def test_receipt_can_only_be_created_by_controlled_factory() -> None:
    with pytest.raises(TypeError):
        KnowledgeSelectionReceipt()  # type: ignore[call-arg]
    receipt = create_selection_receipt(command(), ((claim(), published(), source()),))
    assert receipt.policy_version == "knowledge-selection.v1"
    assert not hasattr(receipt.items[0], "text")
    assert len(receipt.items[0].provenance_hash) == 64


def test_selection_rejects_published_projection_borrowed_from_another_claim() -> None:
    borrowed = replace(published(), claim_id="knowledge:other")
    with pytest.raises(ValueError, match="identity"):
        create_selection_receipt(command(), ((claim(), borrowed, source()),))


@pytest.mark.parametrize(
    "candidate_source,candidate_claim,candidate_command,error",
    [
        (source(verified=False), claim(), command(), "source"),
        (source(status="RETIRED"), claim(), command(), "source"),
        (source(), claim(expires_at=NOW - timedelta(seconds=1)), command(), "expired"),
        (source(), claim(), command(purpose="wrong"), "purpose"),
        (source(), claim(scope="other"), command(), "scope"),
        (
            source(),
            claim(provenance=Provenance(level="E2", source_ref="source:reviewed")),
            command(),
            "evidence",
        ),
    ],
)
def test_selection_rejects_untrusted_candidates(
    candidate_source, candidate_claim, candidate_command, error
) -> None:
    with pytest.raises(ValueError, match=error):
        create_selection_receipt(
            candidate_command, ((candidate_claim, published(), candidate_source),)
        )


def test_source_without_license_is_rejected_at_source_contract() -> None:
    with pytest.raises(ValueError, match="license_ref"):
        source(license_ref="")


def test_receipt_binds_request_fingerprint_scope_and_policy() -> None:
    receipt = create_selection_receipt(command(), ((claim(), published(), source()),))
    assert receipt.request_fingerprint == content_digest("request")
    assert receipt.scope == "family_growth"
    assert receipt.purpose == "family_problem_understanding"
