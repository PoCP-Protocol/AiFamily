"""Real-Postgres proof that a guardian-approved teacher assignment survives.

`authorize_real_teacher_assignment_durable` (`backend.apps.family_api.
orchestration.fgcn_assignment_flow`) is the durable counterpart of the
existing in-memory `authorize_real_teacher_assignment`. This module's only
job is to prove the business claim that matters: once a guardian approves a
real teacher through the Human Gate, the resulting `ServiceCase`/`ServiceTask`
/`TaskAssignment` rows are actually committed to PostgreSQL — not merely held
in one Python process's memory — by re-reading them back through an
independent session after the authorizing session and engine object are gone.

Follows the same opt-in gated pattern as
`tests/domains/family_need/test_postgres_repository_integration.py` and the
`_postgres_fgcn_engine` fixture in `tests/domains/service/fgcn/
test_persistence.py`: every test is skipped unless
``AIFAMILY_TEST_DATABASE_URL`` is set.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.apps.family_api.orchestration.fgcn_assignment_flow import (
    authorize_real_teacher_assignment_durable,
)
from backend.domains.family_need.domain.entities import FamilyConfirmedOutcome
from backend.domains.family_need.domain.value_objects import (
    ActorType,
    DataClass,
    FamilyOutcomeDecision,
    NeedContext,
)
from backend.domains.family_need.infrastructure.fgcn_case_entry_adapter import (
    AsyncFamilyNeedCaseEntryDependencyStub,
)
from backend.domains.service.fgcn.admission import (
    AsyncProviderAdmissionQuery,
    ProviderAdmissionSnapshot,
)
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.persistence import FGCNBase, SqlAlchemyFGCNRepository
from backend.platform.audit import AuditBase
from tests.support.postgres import SKIP_REASON, postgres_test_url

TENANT = "00000000-0000-4000-8000-000000000101"
FAMILY = "00000000-0000-4000-8000-000000000102"
CHILD = "00000000-0000-4000-8000-000000000103"
GUARDIAN_ACTOR_ID = "guardian-durable-1"
PROVIDER_REF = "expert-durable-1"


class _AdmittedProviderAdmission(AsyncProviderAdmissionQuery):
    async def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None:
        return ProviderAdmissionSnapshot(
            provider_ref=provider_ref,
            assignee_kind=assignee_kind,
            admission_status="ACTIVE",
            capability_keys=required_capability_keys,
            allowed_purposes=(scope.purpose,),
            capacity_available=1,
        )


def _scope(*, intent_ref: str) -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=FAMILY,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id=f"corr:{intent_ref}",
    )


def _confirmed_outcome(*, need_id: str, fulfillment_ref: str) -> FamilyConfirmedOutcome:
    context = NeedContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        purpose="FAMILY_NEED",
        consent_version="consent.v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
        subject_person_ids=(CHILD,),
        actor_id=GUARDIAN_ACTOR_ID,
        actor_type=ActorType.FAMILY_GUARDIAN,
    )
    return FamilyConfirmedOutcome.confirm(
        context=context,
        need_id=need_id,
        fulfillment_ref=fulfillment_ref,
        decision=FamilyOutcomeDecision.DID_NOT_HELP,
        confirmed_by=GUARDIAN_ACTOR_ID,
        confirmed_at=datetime(2026, 9, 2, 9, tzinfo=UTC),
    )


@asynccontextmanager
async def _postgres_fgcn_engine():
    """Stand up a disposable Postgres schema with the real FGCN tables.

    Mirrors ``tests/domains/service/fgcn/test_persistence.py``'s
    ``_postgres_fgcn_engine`` fixture exactly (same enum types, same
    hand-authored ``idempotency_keys`` table, same ``FGCNBase``/``AuditBase``
    metadata) so this module tests the identical durable adapter shape
    against a real PostgreSQL server rather than reinventing the schema setup.
    """

    database_url = postgres_test_url()
    if database_url is None:  # pragma: no cover - guarded by the fixture below
        raise RuntimeError(SKIP_REASON)
    schema = f"t_fgcndur_{uuid4().hex[:16]}"
    bootstrap = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            database_url,
            connect_args={
                "statement_cache_size": 0,
                "server_settings": {"search_path": schema},
            },
        )
        try:
            async with engine.begin() as connection:
                for type_name, values in (
                    (
                        "service_case_status",
                        "'OPEN','ASSIGNED','IN_PROGRESS','WAITING_FAMILY','ESCALATED','COMPLETED','CANCELLED'",
                    ),
                    (
                        "service_task_status",
                        "'PENDING','OFFERED','ACCEPTED','IN_PROGRESS','DELIVERED','VERIFIED','CLOSED','CANCELLED','REWORK_REQUESTED'",
                    ),
                    (
                        "task_assignment_status",
                        "'OFFERED','ACCEPTED','DECLINED','REVOKED','COMPLETED'",
                    ),
                    (
                        "task_quality_state",
                        "'PENDING','PASSED','REWORK_REQUIRED','REJECTED'",
                    ),
                ):
                    await connection.execute(text(f"CREATE TYPE {type_name} AS ENUM ({values})"))
                await connection.execute(
                    text(
                        """
                        CREATE TABLE idempotency_keys (
                            idempotency_key varchar(128) PRIMARY KEY,
                            action_name varchar(128) NOT NULL,
                            request_hash varchar(128) NOT NULL,
                            response_code integer NULL,
                            response_body jsonb NULL,
                            created_at timestamptz NOT NULL DEFAULT now(),
                            expires_at timestamptz NULL
                        )
                        """
                    )
                )
                await connection.run_sync(FGCNBase.metadata.create_all)
                await connection.run_sync(AuditBase.metadata.create_all)
            yield engine
        finally:
            await engine.dispose()
    finally:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_real_teacher_assignment_survives_after_the_authorizing_session_closes() -> None:
    """A guardian-approved teacher assignment must be readable from a brand
    new session/connection after the one that created it is gone — proof
    that it lives in PostgreSQL, not merely in the Python process's memory.
    """

    async with _postgres_fgcn_engine() as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        need_id = str(uuid4())
        fulfillment_ref = f"course-completion:{uuid4().hex[:12]}"
        intent_ref = str(uuid4())
        outcome = _confirmed_outcome(need_id=need_id, fulfillment_ref=fulfillment_ref)
        scope = _scope(intent_ref=intent_ref)
        case_entry_dependencies = AsyncFamilyNeedCaseEntryDependencyStub(outcome)
        provider_admission = _AdmittedProviderAdmission()

        # 1. A guardian approves a real teacher assignment. The authorizing
        #    session is opened, used, and closed entirely within this block —
        #    nothing from it is held onto afterwards.
        async with session_factory() as session:
            result = await authorize_real_teacher_assignment_durable(
                session=session,
                scope=scope,
                intent_ref=intent_ref,
                case_entry_dependencies=case_entry_dependencies,
                provider_admission=provider_admission,
                provider_ref=PROVIDER_REF,
                required_capability_keys=(),
                guardian_actor_id=GUARDIAN_ACTOR_ID,
                blueprint_ref=f"blueprint:{intent_ref}",
            )

        assert result.succeeded is True, result.failure_reason
        assert result.failed_step is None
        assert result.assignment_id is not None
        assert result.assignee_ref == PROVIDER_REF

        # 2. Re-query through an entirely independent session — this is the
        #    load-bearing assertion. If the assignment only ever lived in the
        #    `FGCNEngine`/session used above, this second, separate session
        #    would find nothing.
        async with session_factory() as verification_session:
            repo = SqlAlchemyFGCNRepository(verification_session)
            persisted_case = await repo.load_case(result.case_id)
            persisted_task = await repo.load_task(result.task_id)
            persisted_assignment = await repo.load_assignment(result.assignment_id)

        assert persisted_case.case_id == result.case_id
        assert persisted_task.task_id == result.task_id
        assert persisted_task.responsible_ref == PROVIDER_REF
        assert persisted_assignment.assignment_id == result.assignment_id
        assert persisted_assignment.assignee_ref == PROVIDER_REF
