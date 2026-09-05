"""Integration test for `SqlAlchemyAiRunLedger` against a REAL PostgreSQL
instance — verifies `record()` actually writes a row to `ai_run_ledger`
(`database/migrations/0045_ai_run_ledger.sql`), not just that the in-memory
`FakeAiRunLedger` records calls correctly (already covered in
`test_ai_run_ledger.py`).

Requires `PY_ASSESSMENT_TEST_DATABASE_URL` env var pointing at a disposable
PostgreSQL database that already has the schema from
`database/migrations/0001..0045` applied — same convention as
`test_sqlalchemy_repository_integration.py`. Skipped entirely if that env
var is not set.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.domains.assessment.domain.ai_run import AiRunRecord
from backend.domains.assessment.infrastructure.ai_run_ledger import SqlAlchemyAiRunLedger

DATABASE_URL = os.environ.get("PY_ASSESSMENT_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="PY_ASSESSMENT_TEST_DATABASE_URL not set — skipping real-Postgres integration tests",
)


@pytest.fixture
async def connection():
    engine = create_async_engine(DATABASE_URL, poolclass=None)
    async with engine.connect() as conn:
        yield conn
        # SqlAlchemyAiRunLedger.record() commits on its own connection, so
        # there is no in-flight transaction to roll back here — instead we
        # explicitly delete any rows this test wrote, keyed by run_id, so
        # the table is left clean for the next run.
    await engine.dispose()


def _record(run_id: str, outcome: str = "success") -> AiRunRecord:
    now = datetime.now(UTC)
    return AiRunRecord(
        run_id=run_id,
        assessment_session_id="int-test-session",
        service_depth="DEEP_AI_INTERPRETATION",
        generator="gateway",
        model_name="claude-opus-4-8",
        started_at=now,
        completed_at=now,
        input_tokens=42,
        output_tokens=17,
        outcome=outcome,
        error_detail=None if outcome == "success" else "boundary_check_failed",
    )


class TestSqlAlchemyAiRunLedgerRealPostgres:
    async def test_record_writes_a_row_readable_back(self, connection):
        run_id = str(uuid.uuid4())
        ledger = SqlAlchemyAiRunLedger(connection)
        try:
            await ledger.record(_record(run_id))

            result = await connection.execute(
                text(
                    "select assessment_session_id, generator, model_name, outcome, input_tokens, "
                    "output_tokens from ai_run_ledger where run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            row = result.first()
            assert row is not None
            assert row.assessment_session_id == "int-test-session"
            assert row.generator == "gateway"
            assert row.model_name == "claude-opus-4-8"
            assert row.outcome == "success"
            assert row.input_tokens == 42
            assert row.output_tokens == 17
        finally:
            await connection.execute(
                text("delete from ai_run_ledger where run_id = :run_id"), {"run_id": run_id}
            )
            await connection.commit()

    async def test_boundary_violation_outcome_is_persisted(self, connection):
        run_id = str(uuid.uuid4())
        ledger = SqlAlchemyAiRunLedger(connection)
        try:
            await ledger.record(_record(run_id, outcome="boundary_violation"))

            result = await connection.execute(
                text("select outcome, error_detail from ai_run_ledger where run_id = :run_id"),
                {"run_id": run_id},
            )
            row = result.first()
            assert row is not None
            assert row.outcome == "boundary_violation"
            assert row.error_detail == "boundary_check_failed"
        finally:
            await connection.execute(
                text("delete from ai_run_ledger where run_id = :run_id"), {"run_id": run_id}
            )
            await connection.commit()
