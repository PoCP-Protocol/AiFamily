"""Integration tests for `SqlAlchemyAssessmentRepository` against a REAL
PostgreSQL instance — the "not yet verified against a real Postgres
instance" gap explicitly flagged in the previous commit is closed here.

Requires `PY_ASSESSMENT_TEST_DATABASE_URL` env var pointing at a disposable
PostgreSQL database that already has the schema from
`database/migrations/0001..0044` applied (see this task's own verification
notes — do NOT point this at a shared team database; use an isolated
throwaway instance). Skipped entirely if that env var is not set, so this
suite never silently runs against — or fails to run against — the wrong
database.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.domains.assessment.application.commands import (
    AssessmentCommandHandler,
    MutationMeta,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    DecideGrowthHypothesisCommand,
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.queries import AssessmentQueryHandler, GetUi02ProjectionQuery, GetUi03ProjectionQuery
from backend.domains.assessment.infrastructure.deterministic_interpretation import DeterministicInterpretationAdapter
from backend.domains.assessment.infrastructure.sqlalchemy_repository import SqlAlchemyAssessmentRepository

DATABASE_URL = os.environ.get("PY_ASSESSMENT_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="PY_ASSESSMENT_TEST_DATABASE_URL not set — skipping real-Postgres integration tests"
)


@pytest.fixture
async def connection():
    engine = create_async_engine(DATABASE_URL, poolclass=None)
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()  # every test rolls back — no data persists across tests
    await engine.dispose()


async def _seed_family(conn) -> tuple[str, str, str, str]:
    """Seeds a tenant/family/child/consent/policy row set using real SQL, no
    ORM shortcuts — this is deliberately as close to "how a real family gets
    created" as this domain's dependencies require. Returns
    (tenant_id, family_id, child_id, guardian_id) — guardian_id is the actor
    for mutation commands (family_assessment_sessions.started_by_person_id
    etc. are real FKs to persons, not free-text actor ids).
    """
    tenant_id = str(uuid.uuid4())
    family_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    guardian_id = str(uuid.uuid4())

    await conn.execute(
        text(
            "insert into tenants(tenant_id, tenant_ref, display_name, tenant_type) "
            "values (:id, :ref, 'PyVerify Tenant', 'INTERNAL_SANDBOX')"
        ),
        {"id": tenant_id, "ref": f"pyverify-{tenant_id[:8]}"},
    )
    await conn.execute(
        text("insert into families(family_id, display_name, status) values (:id, '测试家庭', 'ACTIVE')"),
        {"id": family_id},
    )
    await conn.execute(
        text(
            "insert into tenant_family_bindings(tenant_id, family_id, status, effective_from) "
            "values (:tenant_id, :family_id, 'ACTIVE', now())"
        ),
        {"tenant_id": tenant_id, "family_id": family_id},
    )
    await conn.execute(
        text(
            "insert into persons(person_id, family_id, person_type, parent_role, display_name) "
            "values (:id, :family_id, 'PARENT', 'GUARDIAN', '测试家长')"
        ),
        {"id": guardian_id, "family_id": family_id},
    )
    await conn.execute(
        text(
            "insert into persons(person_id, family_id, person_type, display_name) "
            "values (:id, :family_id, 'CHILD', '测试孩子')"
        ),
        {"id": child_id, "family_id": family_id},
    )
    await conn.execute(
        text(
            "insert into consents(family_id, subject_person_id, guardian_person_id, purpose, status, policy_version, granted_at) "
            "values (:family_id, :subject_id, :guardian_id, 'ASSESSMENT', 'GRANTED', 'PYVERIFY_V1', now())"
        ),
        {"family_id": family_id, "subject_id": child_id, "guardian_id": guardian_id},
    )
    # `assertFamilyManagePermission` (ported in permission_policy.py /
    # sqlalchemy_repository.py) requires an ACTIVE OWNER_GUARDIAN/GUARDIAN
    # family_membership row for the actor — without this every command call
    # in this suite fails closed with `actor_has_family_manage_permission`.
    await conn.execute(
        text(
            "insert into family_memberships(family_id, person_id, role, status, joined_at) "
            "values (:family_id, :person_id, 'GUARDIAN', 'ACTIVE', now())"
        ),
        {"family_id": family_id, "person_id": guardian_id},
    )
    await conn.execute(
        text(
            "insert into tenant_policy_profiles(tenant_id, policy_version, status, allowed_pages) "
            "values (:tenant_id, 'PYVERIFY_V1', 'ACTIVE', cast(:allowed_pages as jsonb))"
        ),
        {"tenant_id": tenant_id, "allowed_pages": '["UI-02","UI-03"]'},
    )
    return tenant_id, family_id, child_id, guardian_id


def _meta(key: str) -> MutationMeta:
    return MutationMeta(correlation_id="corr-int-1", idempotency_key=key, source="integration-test")


class TestSqlAlchemyRepositoryRealPostgres:
    async def test_full_assessment_lifecycle_against_real_db(self, connection):
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repo)

        start = await commands.start(StartAssessmentCommand(family_id, tenant_id, guardian_id, child_id, None, _meta("i1")))
        assert start["session"]["status"] == "IN_PROGRESS"
        session_id = start["session"]["assessment_session_id"]

        save = await commands.save_response(
            SaveAssessmentResponseCommand(
                family_id, tenant_id, guardian_id, session_id, "FOCUS", "SINGLE_CHOICE", "PARENT_CHILD_COMMUNICATION", _meta("i2")
            )
        )
        assert save["session"]["responses"][0]["response_value"] == "PARENT_CHILD_COMMUNICATION"

        submit = await commands.submit(SubmitAssessmentCommand(family_id, tenant_id, guardian_id, session_id, _meta("i3")))
        assert submit["session"]["status"] == "SUBMITTED"
        assert submit["evidence_id"] is not None

    async def test_start_is_idempotent_against_real_db(self, connection):
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repo)
        meta = _meta("idem-real-1")

        first = await commands.start(StartAssessmentCommand(family_id, tenant_id, guardian_id, child_id, None, meta))
        second = await commands.start(StartAssessmentCommand(family_id, tenant_id, guardian_id, child_id, None, meta))
        assert second["replayed"] is True
        assert second["session"]["assessment_session_id"] == first["session"]["assessment_session_id"]

    async def test_ui02_projection_against_real_db(self, connection):
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        queries = AssessmentQueryHandler(repo, DeterministicInterpretationAdapter())

        projection = await queries.get_ui02_projection(GetUi02ProjectionQuery(family_id, tenant_id, guardian_id))
        assert projection["availability"] == "AVAILABLE"
        assert projection["tool"]["tool_ref"] == "FAMILY_SUPPORT_NEEDS"

    async def test_growth_hypothesis_confirm_creates_intent_against_real_db(self, connection):
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repo)
        queries = AssessmentQueryHandler(repo, DeterministicInterpretationAdapter())
        growth_commands = GrowthHypothesisCommandHandler(repo, DeterministicInterpretationAdapter())

        start = await commands.start(StartAssessmentCommand(family_id, tenant_id, guardian_id, child_id, None, _meta("g1")))
        session_id = start["session"]["assessment_session_id"]
        await commands.save_response(
            SaveAssessmentResponseCommand(
                family_id, tenant_id, guardian_id, session_id, "FOCUS", "SINGLE_CHOICE", "PARENT_CHILD_COMMUNICATION", _meta("g2")
            )
        )
        await commands.submit(SubmitAssessmentCommand(family_id, tenant_id, guardian_id, session_id, _meta("g3")))

        projection = await queries.get_ui03_projection(GetUi03ProjectionQuery(family_id, tenant_id, guardian_id))
        assert projection["availability"] == "READY"
        hypothesis_ref = projection["hypothesis"]["hypothesis_ref"]

        receipt = await growth_commands.decide(
            DecideGrowthHypothesisCommand(
                family_id, tenant_id, guardian_id, session_id, hypothesis_ref, "CONFIRM", "corr-int-2", "decide-real-1"
            )
        )
        assert receipt["outcome"] == "INTENT_CREATED"
        assert receipt["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
