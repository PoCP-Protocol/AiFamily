from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.evaluation.feedback_regression import (
    FeedbackRegressionCase,
    evaluate_feedback_regression,
    persist_feedback_regression_report,
)
from backend.intelligence.experience.run_http import RunScope
from backend.intelligence.experience.run_store import ExperienceRunPersistenceBase
from backend.intelligence.experience.sql_run_ledger import SqlAlchemyExperienceRunLedger


def _case() -> FeedbackRegressionCase:
    return FeedbackRegressionCase(
        case_ref="case-sql-1",
        case_version="feedback-v1",
        feedback_ref="feedback-sql-1",
        feedback_kind="GUARDIAN_EDIT",
        input_contract={"capability_refs": ["practice:morning"]},
        expected_output={"next_step": "记录一次晨间观察"},
        output_schema={
            "type": "object",
            "required": ["next_step"],
            "properties": {"next_step": {"type": "string"}},
        },
        scope_digest="sha256:opaque-scope",
    )


@pytest.mark.asyncio
async def test_feedback_report_survives_sql_session_restart(tmp_path) -> None:
    database = tmp_path / "feedback-regression.db"
    url = f"sqlite+aiosqlite:///{database}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceRunPersistenceBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    scope = RunScope(tenant_id="tenant-sql", family_id="family-sql", subject_ids=("child-sql",))
    report = evaluate_feedback_regression(
        [_case()], lambda case: {"next_step": "记录一次晨间观察"}, case_version="feedback-v1"
    )

    async with sessions() as session:
        async with session.begin():
            ledger = SqlAlchemyExperienceRunLedger(session)
            await ledger.create_draft(
                scope=scope,
                run_id="run-feedback-sql",
                request_ref="agi:need-sql:path-sql",
                draft_payload={"family_need_id": "need-sql", "status": "DRAFT"},
                idempotency_key="create-feedback-sql",
            )
            first = await persist_feedback_regression_report(
                ledger,
                scope=scope,
                run_id="run-feedback-sql",
                report=report,
                idempotency_key="eval-feedback-sql",
            )
        assert first.status == "recorded"
    await engine.dispose()

    restarted_engine = create_async_engine(url)
    restarted_sessions = async_sessionmaker(restarted_engine, expire_on_commit=False)
    try:
        async with restarted_sessions() as session:
            replay = await SqlAlchemyExperienceRunLedger(session).replay(
                scope=scope, run_id="run-feedback-sql"
            )
            evaluations = [
                item for item in replay.entries if item.interaction_type.value == "evaluation"
            ]
            assert len(evaluations) == 1
            assert evaluations[0].payload["report_ref"] == report.report_ref
            assert evaluations[0].payload["release_eligibility"] == "ELIGIBLE"
            with pytest.raises(Exception, match="SCOPE_MISMATCH"):
                await SqlAlchemyExperienceRunLedger(session).replay(
                    scope=RunScope(
                        tenant_id="tenant-sql",
                        family_id="other-family",
                        subject_ids=("child-other",),
                    ),
                    run_id="run-feedback-sql",
                )
    finally:
        await restarted_engine.dispose()
