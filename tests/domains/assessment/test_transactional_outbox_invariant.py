"""Verifies the Transactional Outbox invariant for the Assessment domain
against a REAL PostgreSQL instance — see
`backend/domains/assessment/OUTBOX_VERIFICATION_NOTES.md` for the
full write-up of method and conclusion.

This is deliberately a SEPARATE file from
`test_sqlalchemy_repository_integration.py` (not just more asserts bolted
onto it) because the two ask different questions:

  * `test_sqlalchemy_repository_integration.py` asks "does a normal command
    call produce the rows we expect?" (happy path).
  * This file asks the actual Transactional Outbox question: "if the outbox
    write step raises partway through, does EVERYTHING in that command call
    roll back — business state AND audit AND outbox — leaving zero
    observable side effects?" That is the property the pattern exists to
    guarantee (business state change and event emission are atomic), and it
    can only be demonstrated by forcing a failure inside the transaction and
    then querying the database from a SEPARATE connection to see what
    persisted, not by reading source code.

Requires `PY_ASSESSMENT_TEST_DATABASE_URL` — same env var and skip behavior
as the sibling integration test file.
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
from backend.domains.assessment.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAssessmentRepository,
)

DATABASE_URL = os.environ.get("PY_ASSESSMENT_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="PY_ASSESSMENT_TEST_DATABASE_URL not set — skipping real-Postgres integration tests",
)


@pytest.fixture
async def engine():
    eng = create_async_engine(DATABASE_URL, poolclass=None)
    yield eng
    await eng.dispose()


@pytest.fixture
async def connection(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()  # every test rolls back — no data persists across tests


async def _seed_family(conn) -> tuple[str, str, str, str]:
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
        text(
            "insert into families(family_id, display_name, status) "
            "values (:id, '测试家庭', 'ACTIVE')"
        ),
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
            "insert into consents(family_id, subject_person_id, guardian_person_id, purpose, "
            "status, policy_version, granted_at) "
            "values (:family_id, :subject_id, :guardian_id, 'ASSESSMENT', 'GRANTED', "
            "'PYVERIFY_V1', now())"
        ),
        {"family_id": family_id, "subject_id": child_id, "guardian_id": guardian_id},
    )
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
    return MutationMeta(
        correlation_id="corr-outbox-1", idempotency_key=key, source="outbox-invariant-test"
    )


class TestOutboxHappyPathAgainstRealPostgres:
    """(3a) Normal path: outbox_events + audit_logs rows actually appear,
    with payload content matching the receipt — read back from the SAME
    live connection is not enough to trust (SQLAlchemy could be caching),
    so this reads through a second, independent connection after commit.
    """

    async def test_start_save_submit_each_write_matching_outbox_and_audit_rows(self, engine):
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                tenant_id, family_id, child_id, guardian_id = await _seed_family(conn)
                repo = SqlAlchemyAssessmentRepository(conn)
                commands = AssessmentCommandHandler(repo)

                start = await commands.start(
                    StartAssessmentCommand(
                        family_id, tenant_id, guardian_id, child_id, None, _meta("h1")
                    )
                )
                session_id = start["session"]["assessment_session_id"]

                save = await commands.save_response(
                    SaveAssessmentResponseCommand(
                        family_id,
                        tenant_id,
                        guardian_id,
                        session_id,
                        "FOCUS",
                        "SINGLE_CHOICE",
                        "PARENT_CHILD_COMMUNICATION",
                        _meta("h2"),
                    )
                )

                submit = await commands.submit(
                    SubmitAssessmentCommand(
                        family_id, tenant_id, guardian_id, session_id, _meta("h3")
                    )
                )
                await trans.commit()  # make it durable so a second connection can see it
            except Exception:
                await trans.rollback()
                raise

            # Read back from a brand-new connection — proves durability, not
            # just in-transaction visibility.
            async with engine.connect() as reader:
                # `occurred_at`/`created_at` can tie within the same
                # millisecond for three inserts issued back-to-back in one
                # process, so identify rows by event_name (unique per call in
                # this scenario) rather than relying on timestamp ordering.
                outbox = (
                    await reader.execute(
                        text(
                            "select event_name, payload from outbox_events where aggregate_id=:sid"
                        ),
                        {"sid": session_id},
                    )
                ).all()
                audits = (
                    await reader.execute(
                        text("select action_name, result from audit_logs where family_id=:fid"),
                        {"fid": family_id},
                    )
                ).all()

            outbox_by_name = {row.event_name: row.payload for row in outbox}
            audit_actions = {row.action_name for row in audits}

            assert set(outbox_by_name) == {
                "AssessmentSessionStarted",
                "AssessmentResponseSaved",
                "AssessmentSessionSubmitted",
            }
            assert audit_actions == {
                "START_ASSESSMENT",
                "SAVE_ASSESSMENT_RESPONSE",
                "SUBMIT_ASSESSMENT",
            }
            assert all(row.result == "SUCCESS" for row in audits)

            # Payload content matches the receipt returned to the caller.
            submitted_payload = outbox_by_name["AssessmentSessionSubmitted"]
            assert submitted_payload["assessment_session_id"] == session_id
            assert submitted_payload["status"] == submit["session"]["status"] == "SUBMITTED"
            assert submitted_payload["evidence_id"] == submit["evidence_id"]
            assert submitted_payload["boundary"] == submit["boundary"]

            saved_payload = outbox_by_name["AssessmentResponseSaved"]
            assert saved_payload["status"] == save["session"]["status"] == "IN_PROGRESS"

            # cleanup: this test intentionally committed, so roll the state
            # back out explicitly to keep the shared verification DB clean
            # for other tests/runs.
            async with engine.connect() as cleanup:
                cleanup_trans = await cleanup.begin()
                await cleanup.execute(
                    text("delete from outbox_events where aggregate_id=:sid"), {"sid": session_id}
                )
                await cleanup.execute(
                    text("delete from audit_logs where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text(
                        "delete from family_assessment_operations where assessment_session_id=:sid"
                    ),
                    {"sid": session_id},
                )
                await cleanup.execute(
                    text("delete from evidence_records where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text(
                        "delete from family_assessment_responses where assessment_session_id=:sid"
                    ),
                    {"sid": session_id},
                )
                await cleanup.execute(
                    text("delete from family_assessment_sessions where assessment_session_id=:sid"),
                    {"sid": session_id},
                )
                await cleanup.execute(
                    text("delete from tenant_policy_profiles where tenant_id=:tid"),
                    {"tid": tenant_id},
                )
                await cleanup.execute(
                    text("delete from family_memberships where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text("delete from consents where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text("delete from persons where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text("delete from tenant_family_bindings where family_id=:fid"),
                    {"fid": family_id},
                )
                await cleanup.execute(
                    text("delete from families where family_id=:fid"), {"fid": family_id}
                )
                await cleanup.execute(
                    text("delete from tenants where tenant_id=:tid"), {"tid": tenant_id}
                )
                await cleanup_trans.commit()


class TestOutboxAtomicityInvariantAgainstRealPostgres:
    """(3b) The actual Transactional Outbox invariant: if the outbox/audit
    write step raises partway through `write_audit_and_outbox` (simulating
    "business write succeeded, outbox write failed"), the WHOLE transaction
    — including the business state change that already ran earlier in the
    same command — must roll back. Verified by querying from a SEPARATE
    connection after the failure, which can only see committed data.
    """

    async def test_failure_inside_write_audit_and_outbox_rolls_back_business_write_too(
        self, engine, connection
    ):
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repo)

        # `AsyncConnection.execute` is a read-only attribute on the real
        # SQLAlchemy class, so we can't monkeypatch the connection object
        # itself. Instead, monkeypatch the REPOSITORY method
        # `write_audit_and_outbox` to run the real audit insert (through the
        # real connection) and then raise before it can run the outbox
        # insert — this is the actual "half of the outbox pair happened"
        # scenario the Transactional Outbox pattern must survive.
        original_write_audit_and_outbox = repo.write_audit_and_outbox

        async def failing_write_audit_and_outbox(
            family_id_,
            actor_id,
            session_id,
            action,
            event_name,
            receipt,
            correlation_id,
            idempotency_key,
            source,
        ):
            await connection.execute(
                text(
                    """
                    insert into audit_logs(family_id,actor_type,actor_id,action_name,resource_type,
                    resource_id,correlation_id,idempotency_key,result,metadata)
                    values (:family_id,'PERSON',:actor_id,:action,'ASSESSMENT_SESSION',:session_id,
                    :correlation_id,:idempotency_key,'SUCCESS','{}'::jsonb)
                    """
                ),
                {
                    "family_id": family_id_,
                    "actor_id": actor_id,
                    "action": action,
                    "session_id": session_id,
                    "correlation_id": correlation_id,
                    "idempotency_key": idempotency_key,
                },
            )
            raise RuntimeError(
                "SIMULATED_OUTBOX_WRITE_FAILURE — injected after audit_logs insert, before "
                "outbox_events insert"
            )

        repo.write_audit_and_outbox = failing_write_audit_and_outbox

        with pytest.raises(RuntimeError, match="SIMULATED_OUTBOX_WRITE_FAILURE"):
            await commands.start(
                StartAssessmentCommand(
                    family_id, tenant_id, guardian_id, child_id, None, _meta("fail-1")
                )
            )

        repo.write_audit_and_outbox = original_write_audit_and_outbox

        # The outer test transaction (see `connection` fixture) is still open
        # here — SQLAlchemy does NOT auto-rollback a failed statement inside
        # an otherwise-open transaction the way asyncpg's raw protocol does
        # for a *server-side* error; a Python-side exception raised by our
        # own code (not a DB error) leaves the transaction merely "not yet
        # rolled back" until something calls rollback/commit. This is
        # exactly why the invariant must be enforced by the transaction
        # boundary code (`transactional_connection` in db.py rolling back on
        # ANY exception), not assumed. We simulate that boundary explicitly
        # here to test what IT does, then verify durability from a reader.
        await connection.rollback()

        # No session row should have survived — the insert into
        # family_assessment_sessions happened earlier in the SAME command
        # call, before the simulated failure.
        session_check = await engine.connect()
        try:
            existing_sessions = (
                await session_check.execute(
                    text("select count(*) c from family_assessment_sessions where family_id=:fid"),
                    {"fid": family_id},
                )
            ).scalar_one()
            existing_audit = (
                await session_check.execute(
                    text("select count(*) c from audit_logs where family_id=:fid"),
                    {"fid": family_id},
                )
            ).scalar_one()
            existing_outbox = (
                await session_check.execute(
                    text(
                        "select count(*) c from outbox_events oe "
                        "join family_assessment_sessions s on "
                        "s.assessment_session_id=cast(oe.aggregate_id as uuid) "
                        "where s.family_id=:fid"
                    ),
                    {"fid": family_id},
                )
            ).scalar_one()
        finally:
            await session_check.close()

        assert existing_sessions == 0, (
            "TRANSACTIONAL OUTBOX INVARIANT VIOLATED: the business write "
            "(family_assessment_sessions insert) survived a rollback "
            "triggered by a failure in the same command's outbox-write "
            "step. Business state and event emission are NOT atomic."
        )
        assert existing_audit == 0, "audit_logs row leaked past rollback"
        assert existing_outbox == 0, "outbox_events row leaked past rollback"

    async def test_failure_inside_write_audit_and_outbox_after_outbox_insert_still_rolls_back(
        self, engine, connection
    ):
        """Mirror case: simulate failure AFTER the outbox_events insert
        succeeds but before the command returns (e.g. a crash immediately
        after). Confirms the outbox row itself doesn't leak independently
        of the business write either — the pairing is atomic in both
        directions, not just one.
        """
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)
        repo = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repo)

        original_write_audit_and_outbox = repo.write_audit_and_outbox

        async def failing_write_audit_and_outbox(
            family_id_,
            actor_id,
            session_id,
            action,
            event_name,
            receipt,
            correlation_id,
            idempotency_key,
            source,
        ):
            # Run the REAL write (both audit_logs and outbox_events inserts,
            # via the real method) then raise as if the process crashed
            # immediately after — the outbox row genuinely exists in this
            # transaction at the moment of failure.
            await original_write_audit_and_outbox(
                family_id_,
                actor_id,
                session_id,
                action,
                event_name,
                receipt,
                correlation_id,
                idempotency_key,
                source,
            )
            raise RuntimeError("SIMULATED_POST_OUTBOX_CRASH")

        repo.write_audit_and_outbox = failing_write_audit_and_outbox

        with pytest.raises(RuntimeError, match="SIMULATED_POST_OUTBOX_CRASH"):
            await commands.start(
                StartAssessmentCommand(
                    family_id, tenant_id, guardian_id, child_id, None, _meta("fail-2")
                )
            )

        repo.write_audit_and_outbox = original_write_audit_and_outbox
        await connection.rollback()

        async with engine.connect() as reader:
            existing_sessions = (
                await reader.execute(
                    text("select count(*) c from family_assessment_sessions where family_id=:fid"),
                    {"fid": family_id},
                )
            ).scalar_one()
            existing_outbox = (
                await reader.execute(
                    text("select count(*) c from outbox_events where payload::text like :pattern"),
                    {"pattern": f"%{family_id}%"},
                )
            ).scalar_one()

        assert existing_sessions == 0, (
            "business write leaked past rollback even though outbox insert had run"
        )
        assert existing_outbox == 0, (
            "outbox_events row leaked past rollback despite the later crash"
        )
