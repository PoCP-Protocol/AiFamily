from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.intelligence.family_understanding.contracts import (
    ContextInput,
    FamilyUnderstandingContextV1,
    KnowledgeRef,
    ProblemUnderstandingDraftV1,
)
from backend.intelligence.model_gateway.contracts import AiProvenance

FIXTURE = Path(__file__).parent / "fixtures" / "family_problem_understanding_v1.json"


def fixture_data() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def make_context() -> FamilyUnderstandingContextV1:
    raw = fixture_data()["context"]
    assert isinstance(raw, dict)
    inputs = tuple(ContextInput(**item) for item in raw["inputs"])
    knowledge = tuple(
        KnowledgeRef(**{**item, "limitations": tuple(item["limitations"])})
        for item in raw["knowledge_refs"]
    )
    return FamilyUnderstandingContextV1(
        snapshot_ref=raw["snapshot_ref"],
        tenant_id=raw["tenant_id"],
        family_id=raw["family_id"],
        subject_ref=raw["subject_ref"],
        consent_ref=raw["consent_ref"],
        consent_granted=True,
        expires_at=datetime.fromisoformat(raw["expires_at"]),
        inputs=inputs,
        knowledge_refs=knowledge,
    )


def provenance(context: FamilyUnderstandingContextV1) -> AiProvenance:
    return AiProvenance(
        provider_id="fake-deterministic",
        model="fake-deterministic",
        model_version="1.0.0",
        prompt_version="family-understanding-prompt.v1",
        schema_version="family_problem_understanding.v1",
        context_snapshot_ref=context.snapshot_ref,
        latency_ms=1,
        data_class="SYNTHETIC",
        use_case="family_problem_understanding_v1",
    )


def test_context_serialises_confirmed_text_and_voice_transcript_with_knowledge() -> None:
    context = make_context()
    payload = context.to_gateway_payload()

    assert [item["kind"] for item in payload["inputs"]] == [
        "GUARDIAN_TEXT",
        "VOICE_TRANSCRIPT",
    ]
    assert payload["fixture_only"] is True
    assert payload["instructions"]["canonical_mutation_forbidden"] is True
    assert payload["knowledge_refs"][0]["content_digest"].startswith("sha256:")


def test_machine_derived_transcript_must_be_confirmed_before_model_access() -> None:
    with pytest.raises(ValueError, match="guardian confirmation"):
        ContextInput(
            source_ref="voice-1",
            kind="VOICE_TRANSCRIPT",
            text="synthetic transcript",
            source="synthetic",
            machine_derived=True,
            guardian_confirmed=False,
        )


def test_context_requires_nonexpired_authorisation_and_knowledge() -> None:
    context = make_context()
    with pytest.raises(ValueError, match="expired"):
        replace(context, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(ValueError, match="knowledge_refs"):
        replace(context, knowledge_refs=())
    with pytest.raises(ValueError, match="consent"):
        replace(context, consent_granted=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="SYNTHETIC"):
        replace(context, data_class="FAMILY_PRIVATE_TEXT")  # type: ignore[arg-type]


def test_typed_draft_preserves_unknowns_and_citations_but_cannot_mutate_state() -> None:
    data = fixture_data()
    context = make_context()
    output = data["provider_output"]
    assert isinstance(output, dict)
    draft = ProblemUnderstandingDraftV1.from_gateway_output(
        output,
        provenance=provenance(context),
        context=context,
    )

    assert draft.status == "DRAFT"
    assert draft.requires_human_confirmation is True
    assert draft.may_mutate_business_state is False
    assert draft.unknowns[0].question
    assert draft.hypotheses[0].knowledge_refs == ("knowledge-routine-transition-v1",)
    assert not hasattr(draft, "family_need")
    assert not hasattr(draft, "growth_intent")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        draft.status = "CONFIRMED"  # type: ignore[misc]


def test_citation_outside_context_is_rejected() -> None:
    data = fixture_data()
    context = make_context()
    output = data["provider_output"]
    assert isinstance(output, dict)
    output["hypotheses"][0]["knowledge_refs"] = ["invented-source"]

    with pytest.raises(ValueError, match="outside the authorised context"):
        ProblemUnderstandingDraftV1.from_gateway_output(
            output,
            provenance=provenance(context),
            context=context,
        )


def test_model_cannot_smuggle_canonical_business_state_into_draft() -> None:
    data = fixture_data()
    context = make_context()
    output = data["provider_output"]
    assert isinstance(output, dict)
    output["family_need"] = {"status": "CONFIRMED"}

    with pytest.raises(ValueError, match="forbidden business-state"):
        ProblemUnderstandingDraftV1.from_gateway_output(
            output,
            provenance=provenance(context),
            context=context,
        )
