"""Fail-closed in-memory knowledge registry.

This is an application-facing adapter, not a persistence model.  It provides
the same semantics a database-backed registry must preserve: source ownership,
review/publish transitions, expiry, purpose/scope filtering and evidence gates.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from backend.packages.contracts.evidence import EvidenceLevel

from .contracts import (
    KnowledgeClaim,
    KnowledgeSource,
    KnowledgeStatus,
    meets_evidence_gate,
)


class KnowledgeRegistry:
    """Small deterministic registry suitable for tests and a first adapter."""

    def __init__(
        self,
        *,
        sources: tuple[KnowledgeSource, ...] = (),
        claims: tuple[KnowledgeClaim, ...] = (),
    ) -> None:
        self._sources: dict[str, KnowledgeSource] = {}
        self._claims: dict[str, KnowledgeClaim] = {}
        for source in sources:
            self.register_source(source)
        for claim in claims:
            self.register_claim(claim)

    def register_source(self, source: KnowledgeSource) -> None:
        if source.source_id in self._sources:
            raise ValueError(f"SOURCE_ALREADY_REGISTERED:{source.source_id}")
        self._sources[source.source_id] = source

    def register_claim(self, claim: KnowledgeClaim) -> None:
        if claim.claim_id in self._claims:
            raise ValueError(f"CLAIM_ALREADY_REGISTERED:{claim.claim_id}")
        source = self._sources.get(claim.source_id)
        if source is None:
            raise ValueError(f"SOURCE_NOT_REGISTERED:{claim.source_id}")
        if source.status == "RETIRED":
            raise ValueError(f"SOURCE_RETIRED:{claim.source_id}")
        self._claims[claim.claim_id] = claim

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        return self._sources.get(source_id)

    def get_claim(self, claim_id: str) -> KnowledgeClaim | None:
        return self._claims.get(claim_id)

    def transition_claim(self, claim_id: str, status: KnowledgeStatus) -> KnowledgeClaim:
        claim = self._claims.get(claim_id)
        if claim is None:
            raise ValueError(f"CLAIM_NOT_FOUND:{claim_id}")
        allowed: dict[KnowledgeStatus, set[KnowledgeStatus]] = {
            "INGESTED": {"PARSED", "RETIRED"},
            "PARSED": {"CHUNKED", "RETIRED"},
            "CHUNKED": {"GROUNDED", "RETIRED"},
            "GROUNDED": {"REVIEWED", "RETIRED"},
            "REVIEWED": {"PUBLISHED", "RETIRED"},
            "PUBLISHED": {"RETIRED"},
            "RETIRED": set(),
        }
        if status not in allowed[claim.status]:
            raise ValueError(f"INVALID_CLAIM_TRANSITION:{claim.status}->{status}")
        if status == "PUBLISHED":
            source = self._sources[claim.source_id]
            if not source.verified:
                raise ValueError(f"SOURCE_NOT_VERIFIED:{claim.source_id}")
            if source.status != "ACTIVE":
                raise ValueError(f"SOURCE_RETIRED:{claim.source_id}")
        updated = replace(claim, status=status)
        self._claims[claim_id] = updated
        return updated

    def retrieve_reviewed(
        self,
        *,
        purpose: str,
        scope: str,
        minimum_evidence: EvidenceLevel | None = None,
        establishing_only: bool = False,
        at: datetime | None = None,
    ) -> tuple[KnowledgeClaim, ...]:
        """Return only published, licensed, in-scope claims.

        The model cannot make a claim available merely by naming its ID: source
        status, publication, expiry, purpose and scope are checked here.
        """

        results: list[KnowledgeClaim] = []
        for claim in self._claims.values():
            source = self._sources[claim.source_id]
            if claim.status != "PUBLISHED" or source.status != "ACTIVE" or not source.verified:
                continue
            if claim.is_expired(at=at):
                continue
            if claim.allowed_purposes and purpose not in claim.allowed_purposes:
                continue
            if claim.scope not in {scope, "*"}:
                continue
            if minimum_evidence is not None and not meets_evidence_gate(
                claim.provenance.level,
                minimum_evidence,
            ):
                continue
            if establishing_only and not claim.supports_establishing_claim:
                continue
            results.append(claim)
        return tuple(sorted(results, key=lambda item: item.claim_id))
