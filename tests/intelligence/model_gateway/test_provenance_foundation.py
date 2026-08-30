"""Exclusive tests for the Model Gateway provenance facade."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest

from backend.intelligence.model_gateway.contracts import AiProvenance, TokenUsage
from backend.intelligence.model_gateway.provenance import (
    ModelGatewayProvenance,
    build_provenance,
)


def _required_kwargs() -> dict[str, object]:
    return {
        "provider_id": "provider-test",
        "model": "model-test",
        "model_version": "2026.08",
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "context_snapshot_ref": "context:test-1",
        "latency_ms": 17,
        "data_class": "SYNTHETIC",
        "use_case": "test_use_case",
    }


def test_facade_reuses_the_canonical_gateway_type() -> None:
    assert ModelGatewayProvenance is AiProvenance


def test_factory_builds_the_canonical_complete_record() -> None:
    generated_at = datetime(2026, 8, 30, 12, tzinfo=UTC)
    provenance = build_provenance(
        **_required_kwargs(),
        confidence=0.75,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        generated_at=generated_at,
    )

    assert isinstance(provenance, AiProvenance)
    assert provenance.provider_id == "provider-test"
    assert provenance.model_version == "2026.08"
    assert provenance.confidence == 0.75
    assert provenance.token_usage == TokenUsage(
        prompt_tokens=10, completion_tokens=20, total_tokens=30
    )
    assert provenance.generated_at == generated_at


def test_factory_leaves_provider_confidence_unfabricated() -> None:
    provenance = build_provenance(**_required_kwargs())

    assert provenance.confidence is None
    assert provenance.generated_at.tzinfo is not None


@pytest.mark.parametrize("field_name", ["provider_id", "model", "prompt_version"])
def test_factory_preserves_canonical_required_field_validation(field_name: str) -> None:
    values = _required_kwargs()
    values[field_name] = ""

    with pytest.raises(ValueError, match="incomplete"):
        build_provenance(**values)


def test_evidence_provenance_remains_a_distinct_domain_contract() -> None:
    from backend.packages.contracts.evidence import Provenance as EvidenceProvenance

    assert EvidenceProvenance is not ModelGatewayProvenance


def test_family_api_main_has_a_clean_import_closure() -> None:
    module = import_module("backend.apps.family_api.main")

    assert module.app.title == "AiFamily family_api"
