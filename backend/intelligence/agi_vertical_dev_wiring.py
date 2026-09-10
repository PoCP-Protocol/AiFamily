"""Explicit development/test composition for the vertical family-growth runtime.

This adapter is deliberately limited to ``test``/``development``.  It uses
the normal ModelGateway admission and schema-validation path with an
in-process provider, while keeping the same ports used by production.
"""

from __future__ import annotations

from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    FamilyGrowthContext,
    PublishedKnowledge,
    VerticalFamilyGrowthRuntime,
)
from backend.intelligence.capability_registry.contracts import CapabilityOffer
from backend.intelligence.capability_registry.registry import CapabilityRegistry
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.packages.contracts.evidence import Provenance


class _Context:
    async def read(self, *, family_id: str, context_snapshot_ref: str) -> FamilyGrowthContext:
        return FamilyGrowthContext(
            tenant_id=family_id,
            family_id=family_id,
            subject_ids=(f"subject:{family_id}",),
            purpose="vertical_family_growth",
            consent_version="consent-v1",
            context_snapshot_ref=context_snapshot_ref,
            values={"focus": "家庭成长", "need_type": "HABIT", "required_capability_keys": ()},
        )


class _Knowledge:
    def __init__(self) -> None:
        source = KnowledgeSource(
            "vertical-dev-source",
            "Reviewed guidance",
            "internal",
            "AiFamily",
            "family_growth",
            True,
        )
        claim = KnowledgeClaim(
            "vertical-growth.v1",
            "将家庭目标拆成可完成的小步，并通过复盘持续调整。",
            source.source_id,
            Provenance(level="E3", source_ref=source.source_id),
            "family_growth",
            allowed_purposes=("vertical_family_growth",),
        )
        self._registry = KnowledgeRegistry(sources=(source,), claims=(claim,))
        for status in ("PARSED", "CHUNKED", "GROUNDED", "REVIEWED", "PUBLISHED"):
            self._registry.transition_claim(claim.claim_id, status)

    async def published(self, *, ref: str) -> PublishedKnowledge | None:
        claim = self._registry.retrieve_reviewed(
            purpose="vertical_family_growth", scope="family_growth"
        )
        item = next((value for value in claim if value.claim_id == ref), None)
        if item is None:
            return None
        import hashlib

        return PublishedKnowledge(
            ref=item.claim_id,
            version=str(item.metadata.get("version", "v1")),
            source=item.source_id,
            applicability=item.scope,
            digest=hashlib.sha256(item.text.encode()).hexdigest(),
            content=item.text,
        )


class _Capabilities:
    def __init__(self) -> None:
        offer = CapabilityOffer(
            "family-habit-practice",
            "v1",
            "家庭习惯微行动",
            "以低风险微行动支持家庭成长复盘。",
            "growth_path_design",
            "family_growth",
            owner="aifamily",
            need_types=("HABIT",),
        )
        self._registry = CapabilityRegistry((offer,))
        self._registry.transition(offer.capability_ref, offer.version, "REVIEWED")
        self._registry.transition(offer.capability_ref, offer.version, "PUBLISHED")

    def retrieve_published(self, **kwargs):  # noqa: ANN003
        return self._registry.retrieve_published(**kwargs)


class _Feedback:
    async def latest(self, *, family_need_id: str) -> tuple[str, ...]:
        return ()


class DevVerticalConsent:
    """Revocable consent adapter for the development vertical runtime.

    The dev runtime must remain production-shaped: every generation performs a
    live consent read.  Keeping revocation state here lets tests and local
    operators exercise the same fail-closed path as a real consent store,
    without pretending that an in-memory grant is durable consent.
    """

    def __init__(self) -> None:
        self._revoked_families: set[str] = set()

    async def is_current(self, *, family_id: str, **kwargs) -> bool:  # noqa: ANN003
        return family_id not in self._revoked_families

    def revoke(self, family_id: str) -> None:
        if not family_id.strip():
            raise ValueError("family_id must not be empty")
        self._revoked_families.add(family_id)

    def restore(self, family_id: str) -> None:
        self._revoked_families.discard(family_id)


class _DefaultProviderGateway:
    """Dev-only selector preserving explicit provider admission in the gateway."""

    def __init__(self, gateway) -> None:  # noqa: ANN001
        self._gateway = gateway

    async def generate_structured(self, request, *, provider_id=None):  # noqa: ANN001
        return await self._gateway.generate_structured(
            request,
            provider_id=provider_id or "fake-deterministic",
        )


def build_dev_vertical_family_growth_runtime(*, environment: str) -> VerticalFamilyGrowthRuntime:
    """Build the normal vertical runtime for an explicitly non-production env."""

    if environment not in {"dev", "test", "development"}:
        raise ValueError("development vertical wiring is not permitted")
    provider = FakeProvider(
        provider_id="fake-deterministic",
        responses_by_use_case={
            "vertical_family_growth": {
                "understanding": "当前家庭成长目标需要先形成共识。",
                "next_step": "选择一个十分钟内可完成的微行动。",
                "path": [{"capability_ref": "family-habit-practice", "version": "v1"}],
            }
        },
    )
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-internal",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        sub_delegates=False,
        minor_data_allowed=True,
        private_text_allowed=True,
        security_assessment_ref="N/A: in-process",
        processing_agreement_ref="N/A: in-process",
        deletion_on_termination_committed=True,
        processing_region="in_process",
    )
    gateway = build_gateway(
        environment=environment,
        providers={provider.provider_id: provider},
        registry=ProviderRegistry((record,)),
    )
    return VerticalFamilyGrowthRuntime(
        gateway=_DefaultProviderGateway(gateway),
        context=_Context(),
        knowledge=_Knowledge(),
        feedback=_Feedback(),
        ledger=EvaluationLedger(),
        capabilities=_Capabilities(),
        consent=DevVerticalConsent(),
    )


__all__ = ["DevVerticalConsent", "build_dev_vertical_family_growth_runtime"]
