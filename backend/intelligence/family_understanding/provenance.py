"""Content-addressed provenance references for AIR understanding drafts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UnderstandingProvenanceBinding:
    """The immutable inputs covered by a public AIR provenance reference."""

    artifact_hash: str
    draft_version: int
    output_schema: dict[str, Any]
    context_snapshot_ref: str
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str

    def __post_init__(self) -> None:
        required = {
            "artifact_hash": self.artifact_hash,
            "context_snapshot_ref": self.context_snapshot_ref,
            "provider_id": self.provider_id,
            "model": self.model,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"provenance binding missing required fields: {missing}")
        if self.draft_version < 1:
            raise ValueError("draft_version must be positive")
        if not self.output_schema:
            raise ValueError("output_schema is required")
        if not self.source_refs:
            raise ValueError("source_refs are required")
        if not self.evidence_refs:
            raise ValueError("evidence_refs are required")
        if any(not ref.strip() for ref in (*self.source_refs, *self.evidence_refs)):
            raise ValueError("source_refs and evidence_refs cannot contain blank values")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "artifact_hash": self.artifact_hash,
            "draft_version": self.draft_version,
            "output_schema": self.output_schema,
            "context_snapshot_ref": self.context_snapshot_ref,
            "source_refs": self.source_refs,
            "evidence_refs": self.evidence_refs,
            "provider_id": self.provider_id,
            "model": self.model,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }

    @property
    def provenance_ref(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"air-provenance:v1:sha256:{hashlib.sha256(encoded).hexdigest()}"
