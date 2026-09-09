"""Explicit composition contract for the vertical family-growth runtime.

The vertical runtime is intentionally assembled in one place.  This module
does not create synthetic dependencies and does not expose a second business
router; the family API composition root may install the resulting bundle on an
application after selecting its environment-specific adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.agi_vertical_runtime import (
    CapabilityPort,
    ConsentPort,
    ContextPort,
    EvaluationLedger,
    FamilyGrowthContext,
    FeedbackPort,
    KnowledgePort,
    ModelGatewayPort,
    PublishedKnowledge,
    VerticalFamilyGrowthRuntime,
)


@dataclass(frozen=True, slots=True)
class VerticalFamilyGrowthComposition:
    """All ports required by one vertical runtime instance."""

    gateway: ModelGatewayPort
    context: ContextPort
    knowledge: KnowledgePort
    feedback: FeedbackPort
    ledger: EvaluationLedger
    capabilities: CapabilityPort | None = None
    consent: ConsentPort | None = None

    def build_runtime(self) -> VerticalFamilyGrowthRuntime:
        return VerticalFamilyGrowthRuntime(
            gateway=self.gateway,
            context=self.context,
            knowledge=self.knowledge,
            feedback=self.feedback,
            ledger=self.ledger,
            capabilities=self.capabilities,
            consent=self.consent,
        )


class _DevelopmentContextPort:
    async def read(self, *, family_id: str, context_snapshot_ref: str) -> FamilyGrowthContext:
        return FamilyGrowthContext(
            tenant_id=family_id,
            family_id=family_id,
            subject_ids=(f"dev-child:{family_id}",),
            purpose="family-growth-understanding",
            consent_version="dev-consent-v1",
            context_snapshot_ref=context_snapshot_ref,
            values={
                "data_class": "SYNTHETIC",
                "need_type": "routine",
                "focus": "家庭成长启动",
                "source": "development_adapter",
            },
        )


class _DevelopmentKnowledgePort:
    async def published(self, *, ref: str) -> PublishedKnowledge | None:
        if ref != "claim:dev-family-growth":
            return None
        return PublishedKnowledge(
            ref=ref,
            version="1",
            source="source:dev-reviewed",
            applicability="family_growth",
            digest="dev-family-growth-digest",
            content="将家庭目标拆成可观察、可复盘的小步行动。",
        )


class _DevelopmentFeedbackPort:
    async def latest(self, *, family_need_id: str) -> tuple[str, ...]:
        return ()


class _DevelopmentConsentPort:
    async def is_current(
        self,
        *,
        family_id: str,
        subject_ids: tuple[str, ...],
        purpose: str,
        consent_version: str,
    ) -> bool:
        return bool(family_id and subject_ids and purpose and consent_version)


class _DevelopmentGateway:
    def __init__(self, gateway: ModelGatewayPort) -> None:
        self._gateway = gateway

    async def generate_structured(self, request, *, provider_id: str | None = None):
        return await self._gateway.generate_structured(
            request, provider_id=provider_id or "fake-deterministic"
        )


def build_development_vertical_family_growth_runtime() -> VerticalFamilyGrowthRuntime:
    """Build the complete dev/test runtime with the production-shaped seams.

    This adapter is intentionally synthetic and must only be called from an
    explicitly allowed development environment.  It keeps the same Gateway,
    knowledge/capability publication, consent and draft-only contracts as a
    real deployment; only external data and model side effects are replaced.
    """

    from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry
    from backend.intelligence.model_gateway.gateway import build_gateway
    from backend.intelligence.model_gateway.provider_registry import (
        ProviderRecord,
        ProviderRegistry,
    )
    from backend.intelligence.model_gateway.providers.fake import FakeProvider

    registry = ProviderRegistry(
        (
            ProviderRecord(
                provider_id="fake-deterministic",
                vendor="aifamily-internal",
                model="fake-deterministic",
                model_version="1.0.0",
                status="INTERNAL_APPROVED",
                approved_environments=("development", "test"),
                sub_delegates=False,
                minor_data_allowed=True,
                private_text_allowed=True,
                security_assessment_ref="N/A: in-process",
                processing_agreement_ref="N/A: in-process",
                deletion_on_termination_committed=True,
                processing_region="in_process",
            ),
        )
    )

    gateway = build_gateway(
        environment="development",
        providers={
            "fake-deterministic": FakeProvider(
                provider_id="fake-deterministic",
                responses_by_use_case={
                    "vertical_family_growth": {
                        "understanding": "家庭当前需要一个可执行的成长起点",
                        "next_step": "完成一次十分钟家庭行动并记录观察",
                        "path": [
                            {
                                "capability_ref": "practice:family-start",
                                "version": "1",
                                "title": "家庭行动启动练习",
                            }
                        ],
                    }
                },
            )
        },
        registry=registry,
    )
    capabilities = CapabilityRegistry(
        (
            CapabilityOffer(
                capability_ref="practice:family-start",
                version="1",
                title="家庭行动启动练习",
                description="一个可观察、可复盘的家庭微行动。",
                purpose="growth_path_design",
                scope="family_growth",
                need_types=("routine",),
                status="PUBLISHED",
                owner="aifamily-development",
            ),
        )
    )
    return VerticalFamilyGrowthComposition(
        gateway=_DevelopmentGateway(gateway),
        context=_DevelopmentContextPort(),
        knowledge=_DevelopmentKnowledgePort(),
        feedback=_DevelopmentFeedbackPort(),
        ledger=EvaluationLedger(),
        capabilities=capabilities,
        consent=_DevelopmentConsentPort(),
    ).build_runtime()


def install_vertical_family_growth_runtime(
    application: object, runtime: VerticalFamilyGrowthRuntime
) -> None:
    """Install an explicitly composed runtime on an application object.

    FastAPI applications expose ``state`` as a mutable namespace.  Keeping the
    installer framework-light makes the contract testable without importing
    the family API and prevents hidden dependency construction here.
    """

    state = getattr(application, "state", None)
    if state is None:
        raise TypeError("application must expose state")
    state.vertical_family_growth_runtime = runtime


__all__ = [
    "VerticalFamilyGrowthComposition",
    "install_vertical_family_growth_runtime",
]
