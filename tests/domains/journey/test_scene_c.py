from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.family_need.domain.entities import FamilyNeed
from backend.domains.family_need.domain.value_objects import (
    ActorType as FamilyNeedActorType,
)
from backend.domains.family_need.domain.value_objects import (
    DataClass,
    EmotionalGate,
    NeedContext,
    NeedStatus,
)
from backend.domains.journey.api.scene_c_routes import (
    SceneCHttpDependencies,
    build_scene_c_router,
)
from backend.domains.journey.application.scene_c import (
    SCENE_C_BOUNDARY,
    FamilyNeedReader,
    SceneCApplication,
    SceneCConflictError,
    SceneCConsentPort,
    SceneCDeletionReferencePort,
    SceneCForbiddenError,
    SceneCIntentStore,
    SceneCIntentView,
    SceneCScopePort,
    SceneCStoreResult,
    SceneCValidationError,
)
from backend.platform.audit import AuditActionKind, AuditEvent
from backend.platform.consent import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)
from backend.platform.identity import ActorContext, ActorType

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"
FAMILY = "family-a"
SUBJECT = "child-a"
ADULT = "adult-a"
NEED_ID = "need-a"


def _actor(
    *,
    actor_id: str = ADULT,
    actor_type: ActorType = ActorType.HUMAN,
    tenant_id: str = TENANT,
    family_id: str = FAMILY,
    correlation_id: str = "corr-1",
) -> ActorContext:
    del family_id
    return ActorContext(actor_id, actor_type, tenant_id, correlation_id)


def _confirmed_need(*, status: NeedStatus = NeedStatus.CONFIRMED) -> FamilyNeed:
    context = NeedContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        purpose="FAMILY_NEED",
        consent_version="consent-v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
        subject_person_ids=(SUBJECT,),
        actor_id=ADULT,
        actor_type=FamilyNeedActorType.FAMILY_GUARDIAN,
        correlation_id="need-corr-1",
    )
    return FamilyNeed(
        need_id=NEED_ID,
        context=context,
        source_signal_ids=("signal-a",),
        subject_person_ids=(SUBJECT,),
        statement="晚间学习容易发生冲突",
        desired_outcome="先完成一个平稳的小行动",
        status=status,
        emotional_gate=EmotionalGate.E2_SAFE_TO_ACT,
        confirmed_by_actor_id=ADULT if status is NeedStatus.CONFIRMED else None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeScope(SceneCScopePort):
    def __init__(self) -> None:
        self.allowed: set[tuple[str, str, str]] = {(TENANT, FAMILY, ADULT)}

    async def assert_can_access(self, *, actor: ActorContext, family_id: str) -> None:
        if (actor.tenant_id, family_id, actor.actor_id) not in self.allowed:
            raise SceneCForbiddenError("trusted_family_scope_denied")


class FakeConsent(SceneCConsentPort):
    def __init__(self) -> None:
        self.grants: tuple[ConsentGrant, ...] = (
            ConsentGrant(
                consent_id="consent-a",
                subject_person_id=SUBJECT,
                guardian_person_id=ADULT,
                purpose=ConsentPurpose.GROWTH_TRACKING,
                status=ConsentStatus.GRANTED,
                granted_at=NOW,
                subject_age=SubjectAge(10),
                guardian_relation=GuardianRelation.GUARDIAN,
            ),
        )

    async def grants_for(
        self,
        *,
        actor: ActorContext,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose,
    ) -> tuple[ConsentGrant, ...]:
        del actor, family_id
        return tuple(
            grant
            for grant in self.grants
            if grant.subject_person_id == subject_person_id and grant.purpose is purpose
        )

    def withdraw(self) -> None:
        self.grants = tuple(
            replace(grant, status=ConsentStatus.WITHDRAWN) for grant in self.grants
        )


class FakeFamilyNeeds(FamilyNeedReader):
    def __init__(self, need: FamilyNeed) -> None:
        self.needs = {(need.tenant_id, need.family_id, need.need_id): need}

    async def load(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> FamilyNeed | None:
        return self.needs.get((tenant_id, family_id, need_id))


class FakeIntentStore(SceneCIntentStore):
    """Transactional test double for the canonical Intent persistence port."""

    def __init__(self) -> None:
        self.intents: dict[tuple[str, str, str], SceneCIntentView] = {}
        self.operations: dict[tuple[str, str, str, str], tuple[str, SceneCStoreResult]] = {}
        self.audit_events: list[AuditEvent] = []
        self.outbox_events: list[Mapping[str, object]] = []
        self.fail_next_mutation = False

    async def create_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
        outbox_event: Mapping[str, object],
    ) -> SceneCStoreResult:
        operation_key = (intent.tenant_id, intent.family_id, "create", idempotency_key)
        previous = self.operations.get(operation_key)
        if previous is not None:
            if previous[0] != request_hash:
                raise SceneCConflictError("idempotency_key_payload_mismatch")
            return SceneCStoreResult(previous[1].intent, replayed=True)

        existing = next(
            (
                item
                for item in self.intents.values()
                if item.tenant_id == intent.tenant_id
                and item.family_id == intent.family_id
                and item.need_id == intent.need_id
                and item.status == "OPEN"
            ),
            None,
        )
        if existing is not None:
            if existing.next_step != intent.next_step:
                raise SceneCConflictError("family_need_next_step_already_selected")
            result = SceneCStoreResult(existing, replayed=True)
            self.operations[operation_key] = (request_hash, result)
            return result

        self._maybe_fail()
        self.intents[(intent.tenant_id, intent.family_id, intent.intent_id)] = intent
        self.audit_events.append(audit_event)
        self.outbox_events.append(dict(outbox_event))
        result = SceneCStoreResult(intent)
        self.operations[operation_key] = (request_hash, result)
        return result

    async def load(
        self, *, tenant_id: str, family_id: str, intent_id: str
    ) -> SceneCIntentView | None:
        return self.intents.get((tenant_id, family_id, intent_id))

    async def record_read_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
    ) -> SceneCStoreResult:
        operation_key = (intent.tenant_id, intent.family_id, "read", idempotency_key)
        previous = self.operations.get(operation_key)
        if previous is not None:
            if previous[0] != request_hash:
                raise SceneCConflictError("idempotency_key_payload_mismatch")
            return SceneCStoreResult(previous[1].intent, replayed=True)
        self.audit_events.append(audit_event)
        result = SceneCStoreResult(intent)
        self.operations[operation_key] = (request_hash, result)
        return result

    async def withdraw_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        actor: ActorContext,
        reason: str,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
        outbox_event: Mapping[str, object],
    ) -> SceneCStoreResult:
        del actor, reason
        operation_key = (intent.tenant_id, intent.family_id, "withdraw", idempotency_key)
        previous = self.operations.get(operation_key)
        if previous is not None:
            if previous[0] != request_hash:
                raise SceneCConflictError("idempotency_key_payload_mismatch")
            return SceneCStoreResult(previous[1].intent, replayed=True)
        if intent.status == "WITHDRAWN":
            result = SceneCStoreResult(intent, replayed=True)
            self.operations[operation_key] = (request_hash, result)
            return result
        self._maybe_fail()
        withdrawn = replace(intent, status="WITHDRAWN")
        key = (intent.tenant_id, intent.family_id, intent.intent_id)
        self.intents[key] = withdrawn
        self.audit_events.append(audit_event)
        self.outbox_events.append(dict(outbox_event))
        result = SceneCStoreResult(withdrawn)
        self.operations[operation_key] = (request_hash, result)
        return result

    def _maybe_fail(self) -> None:
        if self.fail_next_mutation:
            self.fail_next_mutation = False
            raise RuntimeError("simulated_transaction_failure")


class FakeDeletionRefs(SceneCDeletionReferencePort):
    async def refs_for_intent(
        self, *, tenant_id: str, family_id: str, intent_id: str, subject_person_id: str
    ) -> tuple[str, ...]:
        return (f"scene-c:{tenant_id}:{family_id}:{subject_person_id}:{intent_id}",)


def _application(
    *, status: NeedStatus = NeedStatus.CONFIRMED
) -> tuple[SceneCApplication, FakeConsent, FakeIntentStore, FakeScope]:
    consent = FakeConsent()
    store = FakeIntentStore()
    scope = FakeScope()
    app = SceneCApplication(
        scope=scope,
        consent=consent,
        family_needs=FakeFamilyNeeds(_confirmed_need(status=status)),
        intents=store,
        deletion_refs=FakeDeletionRefs(),
        clock=lambda: NOW,
    )
    return app, consent, store, scope


@pytest.mark.asyncio
async def test_choose_readback_withdraw_and_replay_are_one_family_action() -> None:
    app, _, store, _ = _application()
    chosen = await app.choose_next_step(
        actor=_actor(),
        family_id=FAMILY,
        need_id=NEED_ID,
        subject_person_id=SUBJECT,
        next_step="HOME_ACTION",
        idempotency_key="choose-1",
    )
    assert chosen.intent.status == "OPEN"
    assert chosen.intent.boundary == SCENE_C_BOUNDARY
    assert chosen.intent.commercial_intent is False
    assert chosen.deletion_refs

    replay = await app.choose_next_step(
        actor=_actor(correlation_id="retry"),
        family_id=FAMILY,
        need_id=NEED_ID,
        subject_person_id=SUBJECT,
        next_step="HOME_ACTION",
        idempotency_key="choose-1",
    )
    assert replay.replayed is True
    assert replay.intent.intent_id == chosen.intent.intent_id

    readback = await app.readback(
        actor=_actor(correlation_id="read"),
        family_id=FAMILY,
        intent_id=chosen.intent.intent_id,
        idempotency_key="read-1",
    )
    assert readback.intent.status == "OPEN"
    assert any(event.action_kind is AuditActionKind.READ for event in store.audit_events)

    withdrawn = await app.withdraw(
        actor=_actor(correlation_id="withdraw"),
        family_id=FAMILY,
        intent_id=chosen.intent.intent_id,
        reason="家庭决定先暂停",
        idempotency_key="withdraw-1",
    )
    assert withdrawn.intent.status == "WITHDRAWN"
    assert store.outbox_events[-1]["event_name"] == "growth.intent.withdrawn"
    assert store.audit_events[-1].action == "scene_c.intent.withdrawn"

    readback_withdrawn = await app.readback(
        actor=_actor(correlation_id="read-withdrawn"),
        family_id=FAMILY,
        intent_id=chosen.intent.intent_id,
        idempotency_key="read-2",
    )
    assert readback_withdrawn.intent.status == "WITHDRAWN"


@pytest.mark.asyncio
async def test_rejects_ai_unconfirmed_missing_consent_scope_and_commercial_step() -> None:
    app, consent, _, scope = _application()
    with pytest.raises(SceneCForbiddenError, match="human_confirmation_required"):
        await app.choose_next_step(
            actor=_actor(actor_id="agent-1", actor_type=ActorType.AI),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="HOME_ACTION",
            idempotency_key="ai-1",
        )

    unconfirmed, _, _, _ = _application(status=NeedStatus.CLARIFYING)
    with pytest.raises(SceneCConflictError, match="family_need_must_be_confirmed"):
        await unconfirmed.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="HOME_ACTION",
            idempotency_key="unconfirmed-1",
        )

    consent.withdraw()
    with pytest.raises(SceneCForbiddenError, match="growth_tracking_consent_required"):
        await app.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="HOME_ACTION",
            idempotency_key="consent-1",
        )

    scope.allowed.clear()
    with pytest.raises(SceneCForbiddenError, match="trusted_family_scope_denied"):
        await app.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="ASK_FOR_HELP",
            idempotency_key="scope-1",
        )

    with pytest.raises(SceneCValidationError, match="next_step_not_available"):
        await app.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="PURCHASE_NOW",
            idempotency_key="commercial-1",
        )


@pytest.mark.asyncio
async def test_idempotency_conflict_and_withdraw_after_consent_revocation() -> None:
    app, consent, store, _ = _application()
    first = await app.choose_next_step(
        actor=_actor(),
        family_id=FAMILY,
        need_id=NEED_ID,
        subject_person_id=SUBJECT,
        next_step="REVIEW_LATER",
        idempotency_key="same-key",
    )
    with pytest.raises(SceneCConflictError, match="idempotency_key_payload_mismatch"):
        await app.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="ASK_FOR_HELP",
            idempotency_key="same-key",
        )

    consent.withdraw()
    with pytest.raises(SceneCForbiddenError, match="growth_tracking_consent_required"):
        await app.readback(
            actor=_actor(correlation_id="read-denied"),
            family_id=FAMILY,
            intent_id=first.intent.intent_id,
            idempotency_key="read-denied",
        )
    withdrawn = await app.withdraw(
        actor=_actor(correlation_id="stop"),
        family_id=FAMILY,
        intent_id=first.intent.intent_id,
        reason="撤回本次家庭下一步",
        idempotency_key="stop-1",
    )
    assert withdrawn.intent.status == "WITHDRAWN"
    assert len(store.outbox_events) == 2


@pytest.mark.asyncio
async def test_mutation_failure_leaves_intent_audit_and_outbox_empty() -> None:
    app, _, store, _ = _application()
    store.fail_next_mutation = True
    with pytest.raises(RuntimeError, match="simulated_transaction_failure"):
        await app.choose_next_step(
            actor=_actor(),
            family_id=FAMILY,
            need_id=NEED_ID,
            subject_person_id=SUBJECT,
            next_step="HOME_ACTION",
            idempotency_key="failure-1",
        )
    assert store.intents == {}
    assert store.audit_events == []
    assert store.outbox_events == []


def test_http_interface_exposes_choose_readback_and_withdraw() -> None:
    app, _, _, _ = _application()

    async def resolve_actor(
        authorization: str | None, family_id: str, correlation_id: str
    ) -> ActorContext:
        if authorization != "Bearer adult":
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="unauthorized")
        return _actor(correlation_id=correlation_id, family_id=family_id)

    fastapi_app = FastAPI()
    fastapi_app.include_router(
        build_scene_c_router(SceneCHttpDependencies(resolve_actor, app))
    )
    with TestClient(fastapi_app) as client:
        headers = {
            "Authorization": "Bearer adult",
            "Idempotency-Key": "http-choose",
            "X-Correlation-ID": "http-corr",
        }
        chosen = client.post(
            f"/families/{FAMILY}/result/next-step-choice",
            json={
                "need_id": NEED_ID,
                "subject_person_id": SUBJECT,
                "next_step": "HOME_ACTION",
            },
            headers=headers,
        )
        assert chosen.status_code == 200, chosen.text
        intent_id = chosen.json()["intent"]["intent_id"]

        readback = client.get(
            f"/families/{FAMILY}/result/next-step-choice/{intent_id}",
            headers={**headers, "Idempotency-Key": "http-read"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["intent"]["status"] == "OPEN"

        withdrawn = client.post(
            f"/families/{FAMILY}/result/next-step-choice/{intent_id}/withdraw",
            json={"reason": "先暂停"},
            headers={**headers, "Idempotency-Key": "http-withdraw"},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["intent"]["status"] == "WITHDRAWN"
