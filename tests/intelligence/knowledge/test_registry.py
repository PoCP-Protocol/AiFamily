from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.intelligence.knowledge.bundle_adapter import (
    adapt_compiled_bundle,
    load_compiled_bundle,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.packages.contracts.evidence import Provenance


def _source(*, verified: bool = True) -> KnowledgeSource:
    return KnowledgeSource(
        source_id="research:parenting:v1",
        title="Reviewed research source",
        license_ref="license:research",
        owner="research-team",
        scope="shared",
        verified=verified,
    )


def _claim(*, level: str = "E6", status: str = "GROUNDED", expires_at=None) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id="claim:1",
        text="A bounded research claim.",
        source_id="research:parenting:v1",
        provenance=Provenance(level=level, source_ref="research:parenting:v1"),  # type: ignore[arg-type]
        scope="family_growth",
        status=status,  # type: ignore[arg-type]
        allowed_purposes=("principal_knowledge_answer",),
        expires_at=expires_at,
    )


def test_claim_cannot_enter_registry_without_registered_source() -> None:
    with pytest.raises(ValueError, match="SOURCE_NOT_REGISTERED"):
        KnowledgeRegistry(claims=(_claim(),))


def test_publish_requires_verified_source_and_retrieval_requires_explicit_publish() -> None:
    registry = KnowledgeRegistry(sources=(_source(verified=False),))
    registry.register_claim(_claim(status="REVIEWED"))

    with pytest.raises(ValueError, match="SOURCE_NOT_VERIFIED"):
        registry.transition_claim("claim:1", "PUBLISHED")
    assert (
        registry.retrieve_reviewed(purpose="principal_knowledge_answer", scope="family_growth")
        == ()
    )


def test_retrieval_filters_purpose_scope_expiry_and_status() -> None:
    registry = KnowledgeRegistry(sources=(_source(),))
    registry.register_claim(_claim(status="REVIEWED"))
    registry.transition_claim("claim:1", "PUBLISHED")

    assert (
        len(registry.retrieve_reviewed(purpose="principal_knowledge_answer", scope="family_growth"))
        == 1
    )
    assert registry.retrieve_reviewed(purpose="other", scope="family_growth") == ()
    assert registry.retrieve_reviewed(purpose="principal_knowledge_answer", scope="other") == ()

    expired = _claim(
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        status="REVIEWED",
    )
    registry = KnowledgeRegistry(sources=(_source(),))
    registry.register_claim(expired)
    registry.transition_claim("claim:1", "PUBLISHED")
    assert (
        registry.retrieve_reviewed(purpose="principal_knowledge_answer", scope="family_growth")
        == ()
    )


def test_non_establishing_levels_are_retrievable_only_as_bounded_context() -> None:
    registry = KnowledgeRegistry(sources=(_source(),))
    registry.register_claim(_claim(level="E0", status="REVIEWED"))
    registry.transition_claim("claim:1", "PUBLISHED")

    assert (
        len(registry.retrieve_reviewed(purpose="principal_knowledge_answer", scope="family_growth"))
        == 1
    )
    assert (
        registry.retrieve_reviewed(
            purpose="principal_knowledge_answer",
            scope="family_growth",
            establishing_only=True,
        )
        == ()
    )


def test_compiled_bundle_adapter_is_reviewable_but_not_implicitly_published() -> None:
    bundle = {
        "schema_version": "KNOWLEDGE_CHAIN_V2",
        "intervention_id": "PARENTING",
        "bundle_version": "sha256:test",
        "theories": [
            {
                "id": "TH-1",
                "title": "Theory",
                "summary": "A bounded summary.",
                "evidence_grade": "E6",
                "source_refs": ["doi:test"],
            }
        ],
        "constructs": [],
        "methods": [],
        "modalities": [],
    }
    claims = adapt_compiled_bundle(bundle, source=_source())
    assert claims[0].claim_id == "PARENTING:THEORY:TH-1"
    assert claims[0].status == "REVIEWED"
    assert claims[0].metadata["source_refs"] == ("doi:test",)


def test_existing_compiled_snapshot_loads_without_becoming_runtime_truth() -> None:
    path = (
        Path(__file__).parents[3]
        / "docs"
        / "13_research"
        / "knowledge_compiled"
        / "effort_process_feedback.json"
    )
    claims = load_compiled_bundle(path, source=_source())
    assert claims
    assert all(claim.status == "REVIEWED" for claim in claims)
