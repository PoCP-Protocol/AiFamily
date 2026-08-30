from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedExperienceScopeResolver,
    AuthenticatedPrincipal,
    ConsentSnapshot,
    ExperienceScopeError,
)
from backend.intelligence.context_engine.contracts import DataClass
from backend.platform.consent.models import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)
from backend.platform.identity.context import TenantContext, TenantStatus
from backend.platform.identity.trusted_context import (
    InMemoryTrustedTenantScopeStore,
    TenantBindingStatus,
    TenantMembershipStatus,
    TenantRole,
    TrustedTenantScope,
    TrustedTenantScopeResolver,
)


def _trusted_scope(*, family_id: str = "family-1") -> TrustedTenantScope:
    return TrustedTenantScope(
        account_id="account-1",
        tenant=TenantContext(tenant_id="tenant-1", status=TenantStatus.ACTIVE),
        family_id=family_id,
        region_id="CN",
        role=TenantRole.TENANT_OWNER,
        membership_status=TenantMembershipStatus.ACTIVE,
        binding_status=TenantBindingStatus.ACTIVE,
    )


def _grant(
    subject_id: str,
    *,
    status: ConsentStatus = ConsentStatus.GRANTED,
) -> ConsentGrant:
    return ConsentGrant(
        consent_id=f"consent:{subject_id}",
        subject_person_id=subject_id,
        guardian_person_id="guardian-1",
        purpose=ConsentPurpose.AI_PERSONALIZATION,
        status=status,
        granted_at=datetime.now(UTC),
        subject_age=SubjectAge(10),
        guardian_relation=GuardianRelation.GUARDIAN,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )


def _resolver(
    *,
    grants: tuple[ConsentGrant, ...],
    family_id: str = "family-1",
) -> AuthenticatedExperienceScopeResolver:
    trusted = _trusted_scope(family_id=family_id)
    trusted_resolver = TrustedTenantScopeResolver(
        InMemoryTrustedTenantScopeStore((trusted,))
    )

    async def principal() -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            account_id="account-1",
            correlation_id="corr-1",
            causation_id="cause-1",
        )

    async def subjects(_: TrustedTenantScope) -> tuple[str, ...]:
        return ("child-1",)

    async def consent(
        _: TrustedTenantScope,
        __: tuple[str, ...],
        ___: ConsentPurpose,
    ) -> ConsentSnapshot:
        return ConsentSnapshot(
            consent_version="consent.v1",
            grants_by_subject={"child-1": grants},
            deletion_ref="delete:tenant-1:family-1",
        )

    return AuthenticatedExperienceScopeResolver(
        principal_resolver=principal,
        trusted_scope_resolver=trusted_resolver,
        subject_ids_resolver=subjects,
        consent_resolver=consent,
        data_class=DataClass.FAMILY_PRIVATE_TEXT,
    )


@pytest.mark.asyncio
async def test_scope_resolver_composes_trusted_chain_and_fresh_consent() -> None:
    resolved = await _resolver(grants=(_grant("child-1"),)).resolve("family-1")

    assert resolved.tenant_id == "tenant-1"
    assert resolved.family_id == "family-1"
    assert resolved.subject_ids == ("child-1",)
    assert resolved.purpose == ConsentPurpose.AI_PERSONALIZATION.value
    assert resolved.consent_granted is True
    assert resolved.data_class is DataClass.FAMILY_PRIVATE_TEXT


@pytest.mark.asyncio
async def test_scope_resolver_denies_missing_or_withdrawn_consent() -> None:
    with pytest.raises(ExperienceScopeError, match="CONSENT_REQUIRED"):
        await _resolver(grants=()).resolve("family-1")
    with pytest.raises(ExperienceScopeError, match="CONSENT_REQUIRED"):
        await _resolver(grants=(_grant("child-1", status=ConsentStatus.WITHDRAWN),)).resolve(
            "family-1"
        )


@pytest.mark.asyncio
async def test_scope_resolver_denies_unknown_family_before_context_creation() -> None:
    with pytest.raises(ExperienceScopeError, match="TENANT_SCOPE_UNAVAILABLE"):
        await _resolver(grants=(_grant("child-1"),)).resolve("other-family")


def test_consent_snapshot_is_immutable_after_construction() -> None:
    grants = {"child-1": (_grant("child-1"),)}
    snapshot = ConsentSnapshot(
        consent_version="consent.v1",
        grants_by_subject=grants,
        deletion_ref="delete:tenant-1:family-1",
    )
    grants.clear()

    assert snapshot.grants_for("child-1")
    with pytest.raises(TypeError):
        snapshot.grants_by_subject["child-2"] = ()  # type: ignore[index]
