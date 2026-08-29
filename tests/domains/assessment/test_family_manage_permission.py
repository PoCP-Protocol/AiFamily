"""Tests for the RBAC half of `assert_tenant_family_scope` — the port of
`assertFamilyManagePermission` (`apps/api/src/modules/family/family-permission.ts`)
that was previously a tracked-but-unported gap in `SqlAlchemyAssessmentRepository`
(and, symmetrically, in `FakeAssessmentRepository`).

Exercises both pass conditions from the NestJS source, independently:
  1. legacy `CreateFamily` audit success for (family_id, actor_id)
  2. an ACTIVE `OWNER_GUARDIAN`/`GUARDIAN` family_membership for actor_id
and the reject path when neither holds.
"""
from __future__ import annotations

import uuid

import pytest

from backend.domains.assessment.domain.errors import AssessmentForbiddenError
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository

TENANT_ID = "tenant-1"


@pytest.fixture
def family_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def repo(family_id: str) -> FakeAssessmentRepository:
    repository = FakeAssessmentRepository()
    repository.seed_family(TENANT_ID, family_id)
    return repository


class TestAssertFamilyManagePermission:
    async def test_owner_guardian_membership_passes(self, repo: FakeAssessmentRepository, family_id: str):
        actor_id = str(uuid.uuid4())
        repo.grant_family_manage_permission(family_id, actor_id, role="OWNER_GUARDIAN")

        await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)

    async def test_guardian_membership_passes(self, repo: FakeAssessmentRepository, family_id: str):
        actor_id = str(uuid.uuid4())
        repo.grant_family_manage_permission(family_id, actor_id, role="GUARDIAN")

        await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)

    async def test_legacy_create_family_audit_passes_even_without_membership(
        self, repo: FakeAssessmentRepository, family_id: str
    ):
        actor_id = "legacy-creator-actor"
        repo.seed_create_family_audit(family_id, actor_id)

        await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)

    async def test_non_manage_role_membership_is_forbidden(self, repo: FakeAssessmentRepository, family_id: str):
        actor_id = str(uuid.uuid4())
        # ADULT_MEMBER / CHILD_SUBJECT are valid family_memberships roles but
        # not in the manage-permission allow-list (`role in ('OWNER_GUARDIAN',
        # 'GUARDIAN')` in family-permission.ts).
        repo.grant_family_manage_permission(family_id, actor_id, role="ADULT_MEMBER")

        with pytest.raises(AssessmentForbiddenError) as exc_info:
            await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)
        assert exc_info.value.code == "actor_has_family_manage_permission"

    async def test_actor_with_no_audit_and_no_membership_is_forbidden(
        self, repo: FakeAssessmentRepository, family_id: str
    ):
        actor_id = str(uuid.uuid4())

        with pytest.raises(AssessmentForbiddenError) as exc_info:
            await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)
        assert exc_info.value.code == "actor_has_family_manage_permission"

    async def test_membership_in_a_different_family_does_not_grant_permission(
        self, repo: FakeAssessmentRepository, family_id: str
    ):
        other_family_id = str(uuid.uuid4())
        repo.seed_family(TENANT_ID, other_family_id)
        actor_id = str(uuid.uuid4())
        repo.grant_family_manage_permission(other_family_id, actor_id, role="OWNER_GUARDIAN")

        with pytest.raises(AssessmentForbiddenError) as exc_info:
            await repo.assert_tenant_family_scope(TENANT_ID, family_id, actor_id)
        assert exc_info.value.code == "actor_has_family_manage_permission"

    async def test_tenant_family_scope_is_still_checked_before_rbac(
        self, repo: FakeAssessmentRepository, family_id: str
    ):
        # A membership alone must not bypass the tenant_family_bindings gate.
        unbound_family_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())
        repo.grant_family_manage_permission(unbound_family_id, actor_id, role="OWNER_GUARDIAN")

        with pytest.raises(AssessmentForbiddenError) as exc_info:
            await repo.assert_tenant_family_scope(TENANT_ID, unbound_family_id, actor_id)
        assert exc_info.value.code == "tenant_family_scope_denied"

    async def test_default_seeded_test_actor_still_passes(self, repo: FakeAssessmentRepository, family_id: str):
        # Guards the backward-compatibility seam every other test in this
        # suite relies on: `seed_family` pre-grants "actor-1" OWNER_GUARDIAN.
        await repo.assert_tenant_family_scope(TENANT_ID, family_id, "actor-1")
