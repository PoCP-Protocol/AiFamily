"""Explicit synthetic runtime for exercising the production-shaped AI path.

This module is a test/development composition root, not a feature shortcut.
It wires the same context-bound application, provider-neutral router and Model
Gateway used by a real deployment, replacing only the network provider with a
deterministic ``FakeProvider``.  The factory refuses missing scope inputs and
refuses any environment other than ``test``; there is no global family or
tenant fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import uuid4

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.api import (
    MultimodalDraftApplication,
    MultimodalDraftRuntime,
)
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalDraft,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import MultimodalExperienceService
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import deterministic_provider

_SYNTHETIC_PURPOSE = "family-image-summary"
_SYNTHETIC_PROVIDER_ID = "synthetic-deterministic"


def _synthetic_output(request: StructuredRequest) -> dict[str, object]:
    """Return a schema-shaped fixture while keeping the real gateway path visible."""

    if request.schema_version != "family-understanding-draft.v1":
        return {
            "headline": "合成运行时草案",
            "next_step": "由家庭成员确认后再继续",
        }

    turns = request.payload.get("conversation_turns")
    first_turn = turns[0] if isinstance(turns, (list, tuple)) and turns else {}
    source_ref = first_turn.get("input_ref") if isinstance(first_turn, dict) else None
    if not isinstance(source_ref, str) or not source_ref.strip():
        source_ref = request.input_refs[0] if request.input_refs else "input:synthetic"
    expression = request.payload.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        expression = "家长正在描述一个反复出现、希望被认真理解的家庭困扰。"

    return {
        "understanding": {
            "lived_experience": (
                f"你提到“{expression.strip()}”。这不只是一个表面事件，"
                "也包含了反复投入却仍感到无力的体验。"
            ),
            "central_tension": (
                "一边是希望事情尽快回到正轨的现实压力，另一边是家人各自"
                "尚未被说清的感受、节奏与需要。"
            ),
            "care_intent": (
                "你真正想守护的既有孩子的成长，也有家庭成员之间能够理解、合作而不是彼此消耗的关系。"
            ),
        },
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "困难可能集中在事件发生前后的转换与沟通方式。",
                "rationale": (
                    "当前表达显示冲突会反复出现，但还不足以把原因归结为某一个人；"
                    "需要一起辨认触发点、当时的期待和已经尝试过的办法。"
                ),
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": source_ref,
                        "observation": expression.strip(),
                    }
                ],
                "knowledge_refs": ["knowledge:family-transition-reviewed-v1"],
                "confidence": "MEDIUM",
                "disconfirming_evidence_needed": (
                    "如果在节奏宽松、期待已经说清时仍同样发生，就需要重新理解原因。"
                ),
            }
        ],
        "unknowns": [
            {
                "unknown_id": "U1",
                "description": "最近一次相对顺利的相似时刻发生了什么",
                "why_it_matters": "它能帮助发现家庭已经拥有、但尚未被看见的有效条件",
                "related_hypothesis_ids": ["H1"],
            }
        ],
        "follow_up_questions": [
            {
                "question_id": "Q1",
                "question": "最近一次这件事没有升级成冲突时，当时有什么不同？",
                "purpose": "用真实例外校正当前理解，并寻找家庭已有的力量",
                "answers_unknown_ids": ["U1"],
            }
        ],
        "strengths": [
            {
                "statement": "你愿意停下来重新理解问题，而不是简单给家人贴标签。",
                "evidence_refs": [source_ref],
                "why_it_matters": "这为家庭共同修正理解、形成合作创造了空间。",
            }
        ],
        "desired_change": {
            "statement": "希望类似时刻能够减少拉扯，让家人更容易理解彼此并一起处理问题。",
            "basis": "INFERRED",
            "observable_signs": [
                "家庭成员能够说出各自真正担心的事情",
                "同类事件出现时，沟通不再立刻升级为对抗",
            ],
            "confirmation_question": "这是否接近你真正希望家庭发生的变化？",
        },
        "limitations": [
            "当前理解只基于本轮家长表达，需要通过后续回答、修正和家庭真实情境继续验证。"
        ],
    }


@dataclass(frozen=True, slots=True)
class _ScopeBoundSyntheticApplication:
    """Bind the synthetic application to one explicit scope envelope."""

    scope: ContextScope
    delegate: ContextBoundMultimodalExperienceService

    async def generate_draft(
        self, command: ContextBoundMultimodalCommand
    ) -> ContextBoundMultimodalDraft:
        if command.scope != self.scope:
            raise ContextScopeError("SYNTHETIC_RUNTIME_SCOPE_MISMATCH")
        return await self.delegate.generate_draft(command)


@dataclass(frozen=True, slots=True)
class SyntheticRuntimeResolver:
    """Resolve a fresh synthetic runtime for each request path family.

    The resolver intentionally stores no family id.  Tenant and subject scope
    are explicit constructor inputs; ``family_id`` is supplied per call and is
    passed through the same factory validation before a new application graph
    is built.
    """

    tenant_id: str
    subject_ids: tuple[str, ...]
    environment: str = "test"
    run_ledger: InMemoryExperienceRunLedger = field(default_factory=InMemoryExperienceRunLedger)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ValueError("tenant_id must be explicit")
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ValueError("subject_ids must be explicit")
        if any(not isinstance(subject, str) or not subject.strip() for subject in self.subject_ids):
            raise ValueError("subject_ids must contain non-empty ids")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("subject_ids must be unique")
        if self.environment != "test":
            raise ValueError("synthetic runtime only supports the test environment")

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
        """Build a runtime bound to this request's family path."""

        return build_synthetic_runtime(
            family_id=family_id,
            tenant_id=self.tenant_id,
            subject_ids=self.subject_ids,
            environment=self.environment,
            run_ledger=self.run_ledger,
        )


def build_synthetic_runtime(
    family_id: str,
    tenant_id: str | None = None,
    subject_ids: tuple[str, ...] | None = None,
    *,
    environment: str = "test",
    run_ledger: InMemoryExperienceRunLedger | None = None,
) -> MultimodalDraftRuntime:
    """Build a production-shaped runtime backed by deterministic test data.

    ``tenant_id`` and ``subject_ids`` deliberately default to ``None`` only so
    omission produces an explicit error.  They are never replaced with a
    process-wide or demo-family value.  ``environment='production'`` is also a
    hard error: synthetic credentials/data must never be accidentally wired to
    production semantics.
    """

    if not isinstance(family_id, str) or not family_id.strip():
        raise ValueError("family_id must be explicit")
    if tenant_id is None or not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be explicit; synthetic runtime has no global tenant")
    if subject_ids is None:
        raise ValueError("subject_ids must be explicit; synthetic runtime has no global scope")
    if not isinstance(subject_ids, tuple) or not subject_ids:
        raise ValueError("subject_ids must be a non-empty tuple")
    if environment != "test":
        raise ValueError("synthetic runtime only supports the test environment")

    scope = ContextScope(
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=_SYNTHETIC_PURPOSE,
        consent_version="synthetic-consent.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref=f"synthetic-delete:{tenant_id}:{family_id}",
        correlation_id=f"synthetic-correlation:{uuid4()}",
        causation_id=f"synthetic-causation:{uuid4()}",
    )

    provider = deterministic_provider(
        _synthetic_output,
        provider_id=_SYNTHETIC_PROVIDER_ID,
    )
    provider_record = ProviderRecord(
        provider_id=_SYNTHETIC_PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        sub_delegates=False,
        security_assessment_ref="synthetic-test-only",
        processing_agreement_ref="synthetic-test-only",
        deletion_on_termination_committed=True,
        processing_region="local-test",
    )
    gateway = ModelGateway(
        {_SYNTHETIC_PROVIDER_ID: provider},
        environment=environment,
        registry=ProviderRegistry((provider_record,)),
    )
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=_SYNTHETIC_PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=(environment,),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        security_assessment_ref="synthetic-test-only",
        processing_agreement_ref="synthetic-test-only",
        deletion_on_termination_committed=True,
    )
    routed = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(gateway),
    )
    context_bound = ContextBoundMultimodalExperienceService(context=ContextBroker(), routed=routed)
    application: MultimodalDraftApplication = _ScopeBoundSyntheticApplication(
        scope=scope, delegate=context_bound
    )
    return MultimodalDraftRuntime(
        scope=scope,
        application=application,
        environment=environment,
        run_ledger=(run_ledger if run_ledger is not None else InMemoryExperienceRunLedger()),
    )


__all__ = ["SyntheticRuntimeResolver", "build_synthetic_runtime"]
