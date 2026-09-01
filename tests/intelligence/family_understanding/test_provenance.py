from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.family_understanding.provenance import (
    UnderstandingProvenanceBinding,
)


def binding() -> UnderstandingProvenanceBinding:
    return UnderstandingProvenanceBinding(
        artifact_hash="a" * 64,
        draft_version=1,
        output_schema={"type": "object", "required": ["perspective"]},
        context_snapshot_ref="context-1",
        source_refs=("guardian-input-1",),
        evidence_refs=("guardian-input-1", "knowledge-1"),
        provider_id="approved-provider",
        model="model-a",
        model_version="2026-09",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
    )


def test_provenance_ref_is_stable_and_not_an_artifact_or_request_alias() -> None:
    value = binding()

    assert value.provenance_ref == binding().provenance_ref
    assert value.provenance_ref.startswith("air-provenance:v1:sha256:")
    assert value.provenance_ref != value.artifact_hash


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_hash": "b" * 64},
        {"draft_version": 2},
        {"output_schema": {"type": "object", "required": ["unknowns"]}},
        {"context_snapshot_ref": "context-2"},
        {"source_refs": ("guardian-input-2",)},
        {"evidence_refs": ("guardian-input-1", "knowledge-2")},
        {"model_version": "2026-10"},
        {"prompt_version": "prompt-v2"},
    ],
)
def test_each_bound_dimension_changes_the_reference(change: dict[str, object]) -> None:
    original = binding()

    assert replace(original, **change).provenance_ref != original.provenance_ref


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_hash": ""},
        {"draft_version": 0},
        {"output_schema": {}},
        {"context_snapshot_ref": ""},
        {"source_refs": ()},
        {"evidence_refs": ()},
        {"evidence_refs": ("",)},
    ],
)
def test_incomplete_binding_fails_closed(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(binding(), **change)
