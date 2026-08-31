"""SQL persistence for immutable ProductPackage DRAFT review submissions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from sqlalchemy import JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.human_gate.contracts import ActionProposal, ActorType, HumanTask
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.platform.audit import AuditEvent, AuditRecorder

from ..application.product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPTION_PURPOSE,
    ProductDefinitionAdoptionArguments,
)
from ..application.product_package_submission import (
    PRODUCT_PACKAGE_PROCESSING_BASIS,
    ProductPackageSubmissionConflictError,
    ProductPackageSubmissionResult,
)
from ..domain.errors import ProductIntelligenceNotFoundError
from ..domain.product_package_draft import ProductPackageDraftVersion
from .product_definition_adoption_repository import (
    SqlAlchemyProductDefinitionAdoptionRepository,
)
from .sqlalchemy_models import Base, DateTime


class ProductPackageDraftRow(Base):
    __tablename__ = "product_intelligence_product_package_drafts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_scope",
            "actor_id",
            "idempotency_key",
            name="uq_product_package_draft_idempotency",
        ),
    )

    draft_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    tenant_scope: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_draft_locator: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(200), nullable=False)
    task_id: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _draft(row: ProductPackageDraftRow) -> ProductPackageDraftVersion:
    draft = ProductPackageDraftVersion.model_validate(row.payload)
    if row.content_hash != draft.content_hash:
        raise ProductPackageSubmissionConflictError(
            "PRODUCT_PACKAGE_PERSISTED_CONTENT_HASH_MISMATCH"
        )
    return draft


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _immutable_task(task: HumanTask) -> HumanTask:
    proposal = replace(task.proposal, action_arguments=_freeze(task.proposal.action_arguments))
    return replace(task, proposal=proposal)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlAlchemyProductPackageSubmissionRepository:
    """Use one caller-owned session for draft, HumanTask and audit writes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sources = SqlAlchemyProductDefinitionAdoptionRepository(session)
        self._gate = SqlAlchemyHumanGate(session)

    async def load_product_concept(self, entity_id: str, tenant_scope: str):
        return await self._sources.load_product_concept(entity_id, tenant_scope)

    async def load_zone_assessment(self, entity_id: str, tenant_scope: str):
        return await self._sources.load_zone_assessment(entity_id, tenant_scope)

    async def _row_by_key(
        self, *, tenant_scope: str, actor_id: str, idempotency_key: str
    ) -> ProductPackageDraftRow | None:
        return await self._session.scalar(
            select(ProductPackageDraftRow).where(
                ProductPackageDraftRow.tenant_scope == tenant_scope,
                ProductPackageDraftRow.actor_id == actor_id,
                ProductPackageDraftRow.idempotency_key == idempotency_key,
            )
        )

    async def find_exact_replay(
        self,
        *,
        tenant_scope: str,
        actor_id: str,
        idempotency_key: str,
        intent_hash: str,
        request_hash: str,
    ) -> ProductPackageSubmissionResult | None:
        row = await self._row_by_key(
            tenant_scope=tenant_scope,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        if row is None:
            return None
        if row.intent_hash != intent_hash:
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_INTENT_REPLAY_MISMATCH"
            )
        if row.request_hash != request_hash:
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_IDEMPOTENCY_REPLAY_MISMATCH"
            )
        return await self._result(row)

    async def find_intent_replay(
        self,
        *,
        tenant_scope: str,
        actor_id: str,
        idempotency_key: str,
        intent_hash: str,
    ) -> ProductPackageSubmissionResult | None:
        row = await self._row_by_key(
            tenant_scope=tenant_scope,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        if row is None:
            return None
        if row.intent_hash != intent_hash:
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_INTENT_REPLAY_MISMATCH"
            )
        return await self._result(row)

    async def get(self, *, draft_id: str, tenant_scope: str) -> ProductPackageSubmissionResult:
        row = await self._session.scalar(
            select(ProductPackageDraftRow).where(
                ProductPackageDraftRow.draft_id == draft_id,
                ProductPackageDraftRow.tenant_scope == tenant_scope,
            )
        )
        if row is None:
            raise ProductIntelligenceNotFoundError("product_package_draft_not_found")
        return await self._result(row)

    async def _result(self, row: ProductPackageDraftRow) -> ProductPackageSubmissionResult:
        draft = _draft(row)
        task = _immutable_task(await self._gate.get(row.task_id))
        proposal = task.proposal
        arguments = ProductDefinitionAdoptionArguments.model_validate(proposal.action_arguments)
        expected_arguments = ProductDefinitionAdoptionArguments(
            concept_id=draft.concept_id,
            zone_assessment_id=draft.zone_assessment_id,
            source_decision_draft_ref=draft.draft_id,
            product_kind=draft.product_kind,
            duration_days=draft.duration_days,
            primary_contradiction=draft.primary_contradiction,
            demand_ref=draft.demand_ref,
            market_insight_refs=draft.market_insight_refs,
            component_ids=draft.component_ids,
            skill_ids=draft.skill_ids,
            success_metric_ids=draft.success_metric_ids,
            guardrail_ids=draft.guardrail_ids,
            stop_conditions=draft.stop_conditions,
            pause_policy=draft.pause_policy,
            human_gate_policy=draft.human_gate_policy,
        )
        if (
            task.task_id != row.task_id
            or row.version_id != draft.version_id
            or row.tenant_scope != draft.tenant_scope
            or row.actor_id != draft.authored_by
            or row.intent_hash != draft.intent_hash
            or row.source_draft_locator != draft.source_draft_locator
            or row.request_hash != draft.resolved_request_hash
            or _utc(row.created_at) != _utc(draft.created_at)
            or _utc(row.expires_at) != _utc(draft.expires_at)
            or proposal.scope.tenant_id != row.tenant_scope
            or proposal.draft_id != row.draft_id
            or proposal.proposal_id != row.proposal_id
            or proposal.action_name != ADOPT_PRODUCT_DEFINITION_ACTION
            or proposal.scope.purpose != ADOPTION_PURPOSE
            or proposal.scope.consent_version != PRODUCT_PACKAGE_PROCESSING_BASIS
            or proposal.scope.family_id is not None
            or proposal.scope.subject_ids != (draft.concept_id, draft.zone_assessment_id)
            or proposal.allowed_actor_types != (ActorType.OPERATOR,)
            or _utc(proposal.created_at) != _utc(draft.created_at)
            or _utc(proposal.expires_at) != _utc(draft.expires_at)
            or proposal.provenance_ref
            != f"product-package-draft:{draft.draft_id}:{draft.content_hash}"
            or arguments != expected_arguments
        ):
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_PERSISTED_LINEAGE_MISMATCH"
            )
        return ProductPackageSubmissionResult(draft=draft, task=task)

    async def persist_submission(
        self,
        *,
        draft: ProductPackageDraftVersion,
        proposal: ActionProposal,
        task_id: str,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        intent_hash: str,
        source_draft_locator: str,
    ) -> ProductPackageSubmissionResult:
        if (
            draft.intent_hash != intent_hash
            or draft.source_draft_locator != source_draft_locator
            or draft.resolved_request_hash != request_hash
        ):
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_INTENT_PERSISTENCE_LINEAGE_MISMATCH"
            )
        replay = await self.find_exact_replay(
            tenant_scope=draft.tenant_scope,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            intent_hash=intent_hash,
            request_hash=request_hash,
        )
        if replay is not None:
            return ProductPackageSubmissionResult(
                draft=replay.draft,
                task=replay.task,
                replayed=True,
            )

        recorder = AuditRecorder()
        try:
            recorder.record(
                AuditEvent(
                    actor_id=actor_id,
                    tenant_id=draft.tenant_scope,
                    action="CREATE_PRODUCT_PACKAGE_DRAFT",
                    resource_type="ProductPackageDraftVersion",
                    resource_id=draft.draft_id,
                    reason="immutable package draft submitted for PDM operator review",
                    correlation_id=proposal.scope.correlation_id,
                    after={
                        "status": "DRAFT",
                        "version_id": draft.version_id,
                        "content_hash": draft.content_hash,
                        "source_provenance_ref": draft.source_provenance_ref,
                    },
                )
            )
            row = ProductPackageDraftRow(
                draft_id=draft.draft_id,
                version_id=draft.version_id,
                tenant_scope=draft.tenant_scope,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                intent_hash=intent_hash,
                source_draft_locator=source_draft_locator,
                request_hash=request_hash,
                content_hash=draft.content_hash,
                proposal_id=proposal.proposal_id,
                task_id=task_id,
                payload=draft.model_dump(mode="json"),
                created_at=draft.created_at,
                expires_at=draft.expires_at,
            )
            self._session.add(row)
            task = _immutable_task(
                await self._gate.submit(proposal, recorder=recorder, task_id=task_id)
            )
            if task.task_id != task_id:
                raise ProductPackageSubmissionConflictError("PRODUCT_PACKAGE_TASK_ID_MISMATCH")
            await recorder.flush(self._session)
            await self._session.commit()
            return ProductPackageSubmissionResult(draft=draft, task=task)
        except IntegrityError as exc:
            await self._session.rollback()
            replay = await self.find_exact_replay(
                tenant_scope=draft.tenant_scope,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                intent_hash=intent_hash,
                request_hash=request_hash,
            )
            if replay is not None:
                return ProductPackageSubmissionResult(
                    draft=replay.draft,
                    task=replay.task,
                    replayed=True,
                )
            raise ProductPackageSubmissionConflictError(
                "PRODUCT_PACKAGE_CONCURRENT_SUBMISSION_CONFLICT"
            ) from exc
        except BaseException:
            await self._session.rollback()
            raise


__all__ = [
    "ProductPackageDraftRow",
    "SqlAlchemyProductPackageSubmissionRepository",
]
