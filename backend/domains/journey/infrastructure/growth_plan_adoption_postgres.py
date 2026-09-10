"""PostgreSQL adapters for the guardian-adopted growth-plan boundary.

The adapters deliberately reuse the existing AI draft review envelope and the
platform audit/idempotency primitives.  They do not create a second draft
registry or a second family ledger.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_review_wiring import (
    GrowthPlanDraftReviewRow,
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.domains.identity.application.service import IdentityApplicationService
from backend.domains.identity.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIdentityRepository,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.platform.audit import AuditEvent, AuditRecorder, persist_events

from ..application.growth_plan_adoption import (
    AdoptedGrowthPlan,
    AdoptedGrowthPlanRepository,
    GrowthPlanActor,
    GrowthPlanDraftReader,
    ValidatedGrowthPlanDraft,
)
from ..domain.errors import JourneyConflictError


class SqlAlchemyGrowthPlanDraftReader(GrowthPlanDraftReader):
    """Resolve the existing immutable AI review envelope by family scope."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_validated_draft(
        self, *, tenant_id: str, family_id: str, draft_ref: str, version: int
    ) -> ValidatedGrowthPlanDraft | None:
        async with self._session_factory() as session:
            row = await self._find_row(session, tenant_id, family_id, draft_ref)
            if row is None:
                return None
            stored = await self._resolve(session, row)
            if stored.identity.draft_id != draft_ref or version != 1:
                return None
            return await self._validated(session, stored)

    async def load_latest_validated_draft(
        self, *, tenant_id: str, family_id: str
    ) -> ValidatedGrowthPlanDraft | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(GrowthPlanDraftReviewRow)
                    .where(
                        GrowthPlanDraftReviewRow.tenant_id == tenant_id,
                        GrowthPlanDraftReviewRow.family_id == family_id,
                    )
                    .order_by(GrowthPlanDraftReviewRow.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return await self._validated(session, await self._resolve(session, row))

    async def _find_row(
        self, session: AsyncSession, tenant_id: str, family_id: str, draft_ref: str
    ) -> GrowthPlanDraftReviewRow | None:
        return (
            await session.execute(
                select(GrowthPlanDraftReviewRow).where(
                    GrowthPlanDraftReviewRow.tenant_id == tenant_id,
                    GrowthPlanDraftReviewRow.family_id == family_id,
                    GrowthPlanDraftReviewRow.draft_id == draft_ref,
                )
            )
        ).scalar_one_or_none()

    async def _resolve(self, session: AsyncSession, row: GrowthPlanDraftReviewRow) -> Any:
        payload = dict(row.scope_payload)
        scope = ContextScope(
            tenant_id=row.tenant_id,
            region_id=row.region_id,
            family_id=row.family_id,
            subject_ids=(row.subject_person_id,),
            purpose=row.purpose,
            consent_version=row.consent_version,
            consent_granted=True,
            data_class=DataClass(row.data_class),
            locale=row.locale,
            deletion_ref=row.deletion_ref,
            correlation_id=row.generation_correlation_id,
            causation_id=payload.get("generation_causation_id", row.generation_correlation_id),
            content_locale=payload.get("content_locale"),
            model_locale=payload.get("model_locale"),
            policy_locale=payload.get("policy_locale"),
            deletion_state=payload.get("deletion_state", "ACTIVE"),
        )
        return await SqlAlchemyGrowthPlanDraftRegistry(self._session_factory).resolve(
            scope=scope,
            draft_id=row.draft_id,
            now=datetime.now(UTC),
        )

    async def _validated(self, session: AsyncSession, stored: Any) -> ValidatedGrowthPlanDraft:
        intent = (
            (
                await session.execute(
                    text(
                        "select confirmed_by, subject_person_id from growth_intents "
                        "where intent_id=:intent_id and family_id=:family_id"
                    ),
                    {"intent_id": stored.intent_id, "family_id": stored.family_id},
                )
            )
            .mappings()
            .first()
        )
        if intent is None:
            return _validated(stored, subject_refs=(stored.subject_person_id,))
        return _validated(
            stored,
            subject_refs=(str(intent["confirmed_by"]), str(intent["subject_person_id"])),
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyAdoptedGrowthPlanRepository(AdoptedGrowthPlanRepository):
    """Durable, family-scoped and idempotent adoption repository."""

    session_factory: async_sessionmaker[AsyncSession]

    async def get_current(self, *, tenant_id: str, family_id: str) -> AdoptedGrowthPlan | None:
        async with self.session_factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """select * from journey_adopted_growth_plans
                        where tenant_id=:tenant_id and family_id=:family_id"""
                        ),
                        {"tenant_id": tenant_id, "family_id": family_id},
                    )
                )
                .mappings()
                .first()
            )
            return _plan_from_row(row) if row else None

    async def record_read(
        self,
        *,
        actor: GrowthPlanActor,
        subject_person_id: str,
        accessed_fields: tuple[str, ...],
        approval_ref: str,
        correlation_id: str,
    ) -> None:
        recorder = AuditRecorder()
        recorder.record_read(
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            action="ReadFamilyGrowthPlan",
            resource_type="AdoptedGrowthPlan",
            resource_id=actor.family_id,
            subject_person_id=subject_person_id,
            accessed_fields=accessed_fields,
            access_purpose="growth_tracking",
            approval_ref=approval_ref,
            reason="guardian read family growth plan",
            correlation_id=correlation_id,
            subject_is_minor=True,
        )
        async with self.session_factory() as session:
            await recorder.flush(session)
            await session.commit()

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
        audit_event: AuditEvent,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        storage_key = "growth-plan-adopt:" + hashlib.sha256(
            f"{plan.tenant_id}:{idempotency_key}".encode()
        ).hexdigest()
        async with self.session_factory() as session:
            inserted = (
                await session.execute(
                    text(
                        """insert into idempotency_keys
                        (idempotency_key, action_name, request_hash, created_at)
                        values (:key, :action, :hash, :created_at)
                        on conflict (idempotency_key) do nothing
                        returning idempotency_key"""
                    ),
                    {
                        "key": storage_key,
                        "action": "AdoptFamilyGrowthPlanDraft",
                        "hash": request_fingerprint,
                        "created_at": datetime.now(UTC),
                    },
                )
            ).first()
            receipt = (
                (
                    await session.execute(
                        text(
                            "select action_name,request_hash,response_body from idempotency_keys "
                            "where idempotency_key=:key for update"
                        ),
                        {"key": storage_key},
                    )
                )
                .mappings()
                .first()
            )
            if receipt is None:
                raise RuntimeError("growth_plan_adoption_idempotency_missing")
            if (
                receipt["action_name"] != "AdoptFamilyGrowthPlanDraft"
                or receipt["request_hash"] != request_fingerprint
            ):
                raise JourneyConflictError("idempotency_conflict")
            if inserted is None:
                if receipt["response_body"] is None:
                    raise JourneyConflictError("idempotency_receipt_incomplete")
                return _plan_from_dict(dict(receipt["response_body"])), False, True

            existing = (
                (
                    await session.execute(
                        text(
                            "select * from journey_adopted_growth_plans "
                            "where tenant_id=:tenant_id and family_id=:family_id for update"
                        ),
                        {"tenant_id": plan.tenant_id, "family_id": plan.family_id},
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None and existing["draft_ref"] != plan.draft_ref:
                raise JourneyConflictError("active_growth_plan_already_exists")
            stored = _plan_from_row(existing) if existing is not None else plan
            if existing is None:
                await session.execute(
                    text(
                        """insert into journey_adopted_growth_plans
                        (plan_id,tenant_id,family_id,subject_refs,draft_ref,draft_version,
                         model_run_ref,provenance_ref,content_sha256,title,family_goal,
                         why_this_plan,duration,stages,adjustable_choices,selected_choices,
                         unknowns_to_watch,review_rhythm,limitations,status,adopted_by,adopted_at)
                         values (:plan_id,:tenant_id,:family_id,:subject_refs,:draft_ref,
                         :draft_version,
                         :model_run_ref,:provenance_ref,:content_sha256,:title,:family_goal,
                         :why_this_plan,:duration,:stages,:adjustable_choices,:selected_choices,
                         :unknowns_to_watch,:review_rhythm,:limitations,:status,:adopted_by,:adopted_at)"""
                    ),
                    _plan_params(plan),
                )
                await persist_events(session, (audit_event,))
                response = stored.as_dict()
                await session.execute(
                    text(
                        "update idempotency_keys set response_code=200,response_body=:body "
                        "where idempotency_key=:key"
                    ),
                    {"key": storage_key, "body": json.dumps(response, ensure_ascii=False)},
                )
                await session.commit()
                return stored, True, False
            response = stored.as_dict()
            await session.execute(
                text(
                    "update idempotency_keys set response_code=200,response_body=:body "
                    "where idempotency_key=:key"
                ),
                {"key": storage_key, "body": json.dumps(response, ensure_ascii=False)},
            )
            await session.commit()
            return stored, False, False


def _validated(stored: Any, *, subject_refs: tuple[str, ...]) -> ValidatedGrowthPlanDraft:
    return ValidatedGrowthPlanDraft(
        draft_ref=stored.identity.draft_id,
        version=1,
        tenant_id=stored.tenant_id,
        family_id=stored.family_id,
        subject_refs=subject_refs,
        status="VALIDATED_DRAFT",
        model_run_ref=stored.agent_run_id,
        provenance_ref=stored.identity.provenance_ref,
        validation_receipt_ref=f"human-review:{stored.identity.draft_id}",
        validated_by="guardian-review-boundary",
        validated_at=stored.created_at,
        content_sha256=_content_digest(stored.model_draft.draft.output),
        output=stored.model_draft.draft.output,
    )


def _content_digest(output: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _plan_params(plan: AdoptedGrowthPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id,
        "family_id": plan.family_id,
        "subject_refs": _json(plan.subject_refs),
        "draft_ref": plan.draft_ref,
        "draft_version": plan.draft_version,
        "model_run_ref": plan.model_run_ref,
        "provenance_ref": plan.provenance_ref,
        "content_sha256": plan.content_sha256,
        "title": plan.title,
        "family_goal": _json(plan.family_goal),
        "why_this_plan": plan.why_this_plan,
        "duration": _json(plan.duration),
        "stages": _json(plan.stages),
        "adjustable_choices": _json(plan.adjustable_choices),
        "selected_choices": _json(plan.selected_choices),
        "unknowns_to_watch": _json(plan.unknowns_to_watch),
        "review_rhythm": _json(plan.review_rhythm),
        "limitations": _json(plan.limitations),
        "status": plan.status,
        "adopted_by": plan.adopted_by,
        "adopted_at": plan.adopted_at,
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _plan_from_row(row: Any) -> AdoptedGrowthPlan:
    def decoded(name: str) -> Any:
        value = row[name]
        return json.loads(value) if isinstance(value, str) else value

    return _plan_from_dict(
        {
            "plan_id": row["plan_id"],
            "tenant_id": row["tenant_id"],
            "family_id": row["family_id"],
            "subject_refs": decoded("subject_refs"),
            "draft_ref": row["draft_ref"],
            "draft_version": row["draft_version"],
            "model_run_ref": row["model_run_ref"],
            "provenance_ref": row["provenance_ref"],
            "content_sha256": row["content_sha256"],
            "title": row["title"],
            "family_goal": decoded("family_goal"),
            "why_this_plan": row["why_this_plan"],
            "duration": decoded("duration"),
            "stages": decoded("stages"),
            "adjustable_choices": decoded("adjustable_choices"),
            "selected_choices": decoded("selected_choices"),
            "unknowns_to_watch": decoded("unknowns_to_watch"),
            "review_rhythm": decoded("review_rhythm"),
            "limitations": decoded("limitations"),
            "status": row["status"],
            "adopted_by": row["adopted_by"],
            "adopted_at": row["adopted_at"].isoformat(),
        }
    )


def _plan_from_dict(value: dict[str, Any]) -> AdoptedGrowthPlan:
    adopted_at = datetime.fromisoformat(str(value["adopted_at"]))
    if adopted_at.tzinfo is None:
        adopted_at = adopted_at.replace(tzinfo=UTC)
    return AdoptedGrowthPlan(
        plan_id=str(value["plan_id"]),
        tenant_id=str(value["tenant_id"]),
        family_id=str(value["family_id"]),
        subject_refs=tuple(value["subject_refs"]),
        draft_ref=str(value["draft_ref"]),
        draft_version=int(value["draft_version"]),
        model_run_ref=str(value["model_run_ref"]),
        provenance_ref=str(value["provenance_ref"]),
        content_sha256=str(value["content_sha256"]),
        title=str(value["title"]),
        family_goal=dict(value["family_goal"]),
        why_this_plan=str(value["why_this_plan"]),
        duration=dict(value["duration"]),
        stages=tuple(value["stages"]),
        adjustable_choices=tuple(value["adjustable_choices"]),
        selected_choices=dict(value["selected_choices"]),
        unknowns_to_watch=tuple(value["unknowns_to_watch"]),
        review_rhythm=dict(value["review_rhythm"]),
        limitations=tuple(value["limitations"]),
        status=str(value["status"]),
        adopted_by=str(value["adopted_by"]),
        adopted_at=adopted_at,
    )


__all__ = [
    "SqlAlchemyAdoptedGrowthPlanRepository",
    "SqlAlchemyGrowthPlanDraftReader",
    "build_postgres_growth_plan_actor_resolver",
]


def build_postgres_growth_plan_actor_resolver(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Resolve the guardian from the durable Identity session on every call."""

    async def resolve_actor(authorization: str | None, family_id: str):
        from backend.domains.identity.domain.errors import (
            IdentityForbiddenError,
            IdentityUnauthenticatedError,
        )

        from ..api.growth_plan_adoption_routes import GrowthPlanAuthenticationError
        from ..application.growth_plan_adoption import GrowthPlanActor

        async with session_factory() as session:
            service = IdentityApplicationService(SqlAlchemyIdentityRepository(session))
            try:
                identity = await service.resolve_actor(
                    bearer_token=authorization,
                    family_id=family_id,
                )
            except (IdentityUnauthenticatedError, IdentityForbiddenError) as error:
                raise GrowthPlanAuthenticationError() from error

            # The adoption policy and the AI draft scope both use the
            # guardian's canonical person id.  IdentityApplicationService
            # intentionally returns the account business id, so resolve the
            # person through the same bearer session and active membership
            # rather than leaking an account id into a person-scoped action.
            token = authorization[len("Bearer ") :]
            person_rows = (
                await session.execute(
                    text(
                        """
                        SELECT tfb.tenant_id, apb.person_id
                        FROM identity_sessions AS s
                        JOIN account_person_bindings AS apb
                          ON apb.account_id = s.account_ref
                         AND apb.status = 'ACTIVE'
                        JOIN family_memberships AS fm
                          ON fm.person_id = apb.person_id
                         AND fm.family_id = :family_id
                         AND fm.status = 'ACTIVE'
                         AND fm.role IN ('OWNER_GUARDIAN', 'GUARDIAN')
                        JOIN tenant_family_bindings AS tfb
                          ON tfb.family_id = fm.family_id
                         AND tfb.status = 'ACTIVE'
                         AND tfb.effective_from <= CURRENT_TIMESTAMP
                         AND (tfb.effective_to IS NULL OR tfb.effective_to > CURRENT_TIMESTAMP)
                        WHERE s.token_hash = :token_hash
                          AND s.revoked_at IS NULL
                          AND s.expires_at > CURRENT_TIMESTAMP
                        ORDER BY fm.membership_id
                        LIMIT 2
                        """
                    ),
                    {
                        "family_id": family_id,
                        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    },
                )
            ).all()
            if (
                len(person_rows) != 1
                or not str(person_rows[0][0] or "").strip()
                or not str(person_rows[0][1] or "").strip()
            ):
                raise GrowthPlanAuthenticationError("guardian_membership_required")
            return GrowthPlanActor(
                actor_id=str(person_rows[0][1]),
                tenant_id=str(person_rows[0][0]),
                family_id=identity.family_id,
                membership_ref=f"membership:{person_rows[0][1]}:{family_id}",
                consent_ref=f"identity-session:{identity.session_id}",
                actor_type="GUARDIAN",
            )

    return resolve_actor
