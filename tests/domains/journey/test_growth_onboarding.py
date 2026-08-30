from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.domains.journey.application.growth_onboarding import (
    GrowthOnboardingApplication,
    StartGrowthOnboardingCommand,
)
from backend.domains.journey.domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    ConfirmedGrowthIntent,
    GrowthOnboarding,
    GrowthOnboardingConflictError,
    GrowthOnboardingForbiddenError,
    GrowthOnboardingNotFoundError,
    GrowthOnboardingScope,
)
from backend.domains.journey.infrastructure.growth_onboarding_fake import (
    FakeConfirmedGrowthIntentReader,
    FakeGrowthOnboardingConsent,
    FakeGrowthOnboardingPolicy,
    FakeGrowthOnboardingRepository,
    FakeGrowthOnboardingTransaction,
)
from backend.platform.consent import ConsentPurpose, ConsentStatus

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
SCOPE = GrowthOnboardingScope("tenant-a", "family-a", "parent-a")


def _intent(
    *,
    intent_id: str = "intent-a",
    status: str = "OPEN",
    confirmed_by: str | None = "parent-a",
    confirmed_at: datetime | None = NOW,
    boundary: str = CONFIRMED_INTENT_BOUNDARY,
    tenant_id: str = SCOPE.tenant_id,
    family_id: str = SCOPE.family_id,
) -> ConfirmedGrowthIntent:
    return ConfirmedGrowthIntent(
        intent_id=intent_id,
        tenant_id=tenant_id,
        family_id=family_id,
        subject_person_id="child-a",
        need_type="COMMUNICATION_SUPPORT",
        goal_text="先完整听完，再确认彼此听到的内容。",
        required_capability_keys=("CAP_PARENT_CHILD_COMMUNICATION",),
        status=status,
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
        boundary=boundary,
    )


def _app(
    *, intent: ConfirmedGrowthIntent | None = None
) -> tuple[
    GrowthOnboardingApplication,
    FakeGrowthOnboardingTransaction,
    FakeGrowthOnboardingRepository,
]:
    reader = FakeConfirmedGrowthIntentReader([intent or _intent()])
    repository = FakeGrowthOnboardingRepository()
    policy = FakeGrowthOnboardingPolicy()
    policy.allow(SCOPE)
    consent = FakeGrowthOnboardingConsent()
    consent.grant(SCOPE, "child-a", "GROWTH_TRACKING")
    transaction = FakeGrowthOnboardingTransaction(
        intent_reader=reader,
        repository=repository,
        policy=policy,
        consent=consent,
    )
    return GrowthOnboardingApplication(transaction), transaction, repository


def _command(*, key: str = "start-a", intent_id: str = "intent-a") -> StartGrowthOnboardingCommand:
    return StartGrowthOnboardingCommand(
        tenant_id=SCOPE.tenant_id,
        family_id=SCOPE.family_id,
        actor_id=SCOPE.actor_id,
        intent_id=intent_id,
        correlation_id=f"correlation:{key}",
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_confirmed_intent_creates_one_onboarding_and_emits_event() -> None:
    application, transaction, repository = _app()

    response = await application.start(_command())

    onboarding = response["onboarding"]
    event = response["event"]
    assert response["created"] is True
    assert response["replayed"] is False
    assert onboarding["intent_id"] == "intent-a"
    assert onboarding["phase"] == "ONBOARDING"
    assert onboarding["status"] == "ACTIVE"
    assert event["event_name"] == "GrowthOnboardingStarted"
    assert event["intent_id"] == "intent-a"
    assert event["onboarding_id"] == onboarding["onboarding_id"]
    assert len(repository.onboardings) == 1
    assert len(transaction.audit_log) == 1
    assert len(transaction.outbox_events) == 1
    assert transaction.audit_log[0]["reason"]
    assert transaction.audit_log[0]["before"] is None
    assert transaction.audit_log[0]["after"]["intent_id"] == "intent-a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "confirmed_by", "confirmed_at", "boundary"),
    [
        ("OPEN", None, NOW, CONFIRMED_INTENT_BOUNDARY),
        ("CANCELLED", "parent-a", NOW, CONFIRMED_INTENT_BOUNDARY),
        ("OPEN", "parent-a", None, CONFIRMED_INTENT_BOUNDARY),
        ("OPEN", "parent-a", NOW, "AI_DRAFT_NOT_FACT"),
    ],
)
async def test_unconfirmed_intent_is_rejected(
    status: str,
    confirmed_by: str | None,
    confirmed_at: datetime | None,
    boundary: str,
) -> None:
    application, transaction, repository = _app(
        intent=_intent(
            status=status,
            confirmed_by=confirmed_by,
            confirmed_at=confirmed_at,
            boundary=boundary,
        )
    )

    with pytest.raises(GrowthOnboardingNotFoundError, match="confirmed_growth_intent_not_found"):
        await application.start(_command())

    assert repository.onboardings == {}
    assert transaction.audit_log == []
    assert transaction.outbox_events == []


@pytest.mark.asyncio
async def test_idempotency_replays_without_duplicate_side_effects() -> None:
    application, transaction, repository = _app()
    command = _command()

    first = await application.start(command)
    replay = await application.start(command)

    assert replay["replayed"] is True
    assert replay["event"]["event_id"] == first["event"]["event_id"]
    assert len(repository.onboardings) == 1
    assert len(transaction.audit_log) == 1
    assert len(transaction.outbox_events) == 1


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_another_intent() -> None:
    application, transaction, repository = _app()
    await application.start(_command())

    with pytest.raises(GrowthOnboardingConflictError, match="idempotency_conflict"):
        await application.start(_command(intent_id="intent-b"))

    assert len(repository.onboardings) == 1
    assert len(transaction.audit_log) == 1
    assert len(transaction.outbox_events) == 1


@pytest.mark.asyncio
async def test_same_intent_with_a_new_key_stays_unique_and_emits_one_event() -> None:
    application, transaction, repository = _app()

    first = await application.start(_command(key="start-a"))
    second = await application.start(_command(key="start-b"))

    assert second["created"] is False
    assert second["onboarding"]["onboarding_id"] == first["onboarding"]["onboarding_id"]
    assert len(repository.onboardings) == 1
    assert len(transaction.audit_log) == 2
    assert len(transaction.outbox_events) == 1


@pytest.mark.asyncio
async def test_scope_consent_and_human_actor_are_fail_closed() -> None:
    application, transaction, repository = _app()
    transaction.dependencies.consent.grants.clear()
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent:GROWTH_TRACKING"):
        await application.start(_command())

    transaction.dependencies.consent.grant(SCOPE, "child-a", "GROWTH_TRACKING")
    transaction.dependencies.policy.allowed_scopes.clear()
    with pytest.raises(GrowthOnboardingForbiddenError, match="actor_family_scope_denied"):
        await application.start(_command(key="scope-denied"))

    actor_command = StartGrowthOnboardingCommand(
        tenant_id=SCOPE.tenant_id,
        family_id=SCOPE.family_id,
        actor_id="ai:principal",
        intent_id="intent-a",
        correlation_id="correlation:ai",
        idempotency_key="ai-denied",
    )
    with pytest.raises(GrowthOnboardingForbiddenError, match="human_actor_required"):
        await application.start(actor_command)
    assert repository.onboardings == {}
    assert transaction.audit_log == []


@pytest.mark.asyncio
async def test_fake_consent_requires_the_active_tenant_family_binding_window() -> None:
    application, transaction, repository = _app()
    consent = transaction.dependencies.consent
    now = datetime.now(UTC)

    consent.bind(
        SCOPE,
        effective_from=now + timedelta(minutes=1),
    )
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")

    consent.bind(
        SCOPE,
        effective_from=now - timedelta(minutes=2),
        effective_to=now - timedelta(minutes=1),
    )
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")

    assert repository.onboardings == {}
    assert transaction.audit_log == []
    assert application is not None


@pytest.mark.asyncio
async def test_fake_consent_matches_canonical_scope_and_effective_window() -> None:
    current = [NOW]
    consent = FakeGrowthOnboardingConsent(now=lambda: current[0])
    record = consent.grant(
        SCOPE,
        "child-a",
        ConsentPurpose.GROWTH_TRACKING,
        consent_id="consent-a",
        granted_at=NOW,
        effective_from=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    assert record.tenant_id == SCOPE.tenant_id
    assert record.family_id == SCOPE.family_id
    assert record.effective_from == NOW
    assert record.effective_to is None
    assert record.expires_at == NOW + timedelta(hours=1)
    assert consent.query(SCOPE, "child-a", "GROWTH_TRACKING") == [record]
    assert consent.query(
        tenant_id=SCOPE.tenant_id,
        family_id=SCOPE.family_id,
        subject_person_id="child-a",
        purpose=ConsentPurpose.GROWTH_TRACKING,
        active_only=True,
    ) == [record]

    await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")
    assert consent.revoke(SCOPE, "child-a", "GROWTH_TRACKING") == 1
    assert record.status is ConsentStatus.GRANTED
    assert consent.query(SCOPE, "child-a", "GROWTH_TRACKING", active_only=True) == []
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")


@pytest.mark.asyncio
async def test_fake_consent_future_expired_and_withdrawn_grants_fail_closed() -> None:
    current = [NOW]
    consent = FakeGrowthOnboardingConsent(now=lambda: current[0])
    future = consent.grant(
        SCOPE,
        "child-a",
        "GROWTH_TRACKING",
        consent_id="consent-future",
        effective_from=NOW + timedelta(hours=1),
        effective_to=NOW + timedelta(hours=2),
    )
    assert future.status_at(NOW) is ConsentStatus.GRANTED
    assert future.is_active_at(NOW) is False
    assert consent.query(SCOPE, "child-a", "GROWTH_TRACKING", active_only=True) == []
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")

    current[0] = NOW + timedelta(hours=1)
    await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")

    current[0] = NOW + timedelta(hours=2)
    assert future.status_at(current[0]) is ConsentStatus.EXPIRED
    assert future.is_active_at(current[0]) is False
    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")

    withdrawn = consent.grant(
        SCOPE,
        "child-a",
        "GROWTH_TRACKING",
        consent_id="consent-withdrawn",
        granted_at=NOW,
        withdrawn_at=NOW,
    )
    assert withdrawn.status is ConsentStatus.GRANTED
    assert withdrawn.status_at(NOW) is ConsentStatus.WITHDRAWN
    assert withdrawn.is_active_at(NOW) is False
    assert consent.query(SCOPE, "child-a", "GROWTH_TRACKING", active_only=True) == []


@pytest.mark.asyncio
async def test_fake_consent_revoke_and_query_do_not_cross_tenant_or_family() -> None:
    tenant_peer = GrowthOnboardingScope("tenant-b", SCOPE.family_id, "parent-b")
    family_peer = GrowthOnboardingScope(SCOPE.tenant_id, "family-b", "parent-c")
    consent = FakeGrowthOnboardingConsent(now=lambda: NOW)
    consent.grant(SCOPE, "child-a", "GROWTH_TRACKING", consent_id="consent-a")
    consent.grant(
        tenant_peer,
        "child-a",
        "GROWTH_TRACKING",
        consent_id="consent-b",
    )
    consent.grant(
        family_peer,
        "child-a",
        "GROWTH_TRACKING",
        consent_id="consent-c",
    )

    assert consent.query(tenant_peer, "child-a", "GROWTH_TRACKING")
    assert consent.query(family_peer, "child-a", "GROWTH_TRACKING")
    assert consent.revoke(SCOPE, "child-a", "GROWTH_TRACKING") == 1
    assert consent.query(SCOPE, "child-a", "GROWTH_TRACKING", active_only=True) == []
    assert consent.query(tenant_peer, "child-a", "GROWTH_TRACKING", active_only=True)
    assert consent.query(family_peer, "child-a", "GROWTH_TRACKING", active_only=True)

    with pytest.raises(GrowthOnboardingForbiddenError, match="missing_consent"):
        await consent.assert_granted(SCOPE, "child-a", "GROWTH_TRACKING")
    await consent.assert_granted(tenant_peer, "child-a", "GROWTH_TRACKING")
    await consent.assert_granted(family_peer, "child-a", "GROWTH_TRACKING")


@pytest.mark.asyncio
async def test_idempotency_key_is_independent_between_tenants() -> None:
    other_scope = GrowthOnboardingScope("tenant-b", "family-b", "parent-b")
    reader = FakeConfirmedGrowthIntentReader(
        [
            _intent(),
            _intent(
                intent_id="intent-b",
                confirmed_by="parent-b",
                tenant_id=other_scope.tenant_id,
                family_id=other_scope.family_id,
            ),
        ]
    )
    repository = FakeGrowthOnboardingRepository()
    policy = FakeGrowthOnboardingPolicy()
    policy.allow(SCOPE)
    policy.allow(other_scope)
    consent = FakeGrowthOnboardingConsent()
    consent.grant(SCOPE, "child-a", "GROWTH_TRACKING")
    consent.grant(other_scope, "child-a", "GROWTH_TRACKING")
    transaction = FakeGrowthOnboardingTransaction(
        intent_reader=reader,
        repository=repository,
        policy=policy,
        consent=consent,
    )
    application = GrowthOnboardingApplication(transaction)

    first = await application.start(_command(key="same-client-key"))
    second = await application.start(
        StartGrowthOnboardingCommand(
            tenant_id=other_scope.tenant_id,
            family_id=other_scope.family_id,
            actor_id=other_scope.actor_id,
            intent_id="intent-b",
            correlation_id="correlation:other-tenant",
            idempotency_key="same-client-key",
        )
    )

    assert first["created"] is True
    assert second["created"] is True
    assert first["onboarding"]["onboarding_id"] != second["onboarding"]["onboarding_id"]
    assert len(transaction.idempotency) == 2


@pytest.mark.asyncio
async def test_fake_transaction_rolls_back_domain_audit_outbox_and_claim() -> None:
    application, transaction, repository = _app()
    command = _command(key="rollback")

    async def failing_operation(dependencies):
        intent = await dependencies.intent_reader.load_confirmed_growth_intent(
            command.scope, command.intent_id
        )
        assert intent is not None
        await dependencies.repository.save_if_absent(
            GrowthOnboarding.start(command.scope, intent, started_at=NOW)
        )
        raise RuntimeError("onboarding_write_failed")

    with pytest.raises(RuntimeError, match="onboarding_write_failed"):
        await transaction.execute(command, failing_operation)

    assert repository.onboardings == {}
    assert transaction.idempotency == {}
    assert transaction.audit_log == []
    assert transaction.outbox_events == []
    assert application is not None


def test_journey_slice_has_no_direct_assessment_repository_dependency() -> None:
    root = Path(__file__).resolve().parents[3] / "backend/domains/journey"
    files = (
        root / "application/growth_onboarding.py",
        root / "domain/growth_onboarding.py",
        root / "infrastructure/growth_onboarding_fake.py",
        root / "infrastructure/growth_onboarding_postgres.py",
    )
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert all(not name.startswith("backend.domains.assessment") for name in imported)
