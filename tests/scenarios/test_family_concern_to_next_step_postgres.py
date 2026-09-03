from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.domains.assessment.application.commands import (
    AssessmentCommandHandler,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    DecideGrowthHypothesisCommand,
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.queries import (
    AssessmentQueryHandler,
    GetUi03ProjectionQuery,
)
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAssessmentRepository,
)
from backend.intelligence.experience.run_http import RunScope
from backend.intelligence.experience.sql_run_ledger import (
    SessionPerCallExperienceRunLedger,
)
from tests.domains.assessment.test_sqlalchemy_repository_integration import (
    _meta,
    _seed_family,
)

pytest_plugins = ("tests.intelligence.experience.test_multimodal_postgres_http_lifecycle",)


async def test_adult_concern_to_deterministic_result_and_next_step_survives_restart(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    async with engine.begin() as connection:
        tenant_id, family_id, child_id, guardian_id = await _seed_family(connection)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    experience = SessionPerCallExperienceRunLedger(session_factory)
    scope = RunScope(tenant_id, family_id, (guardian_id, child_id))
    await experience.create_draft(
        scope=scope,
        run_id="concern-run",
        request_ref="request:concern-run",
        draft_payload={
            "understanding": "家长希望写作业开始时少一些催促和争吵。",
            "hypotheses": [{"statement": "活动转换方式可能影响开始。"}],
        },
        idempotency_key="create:concern-run",
    )
    prior = await experience.replay(scope=scope, run_id="concern-run")
    await experience.create_draft(
        scope=scope,
        run_id="follow-up-run",
        request_ref="request:follow-up-run",
        draft_payload={
            "prior_run_id": prior.run_id,
            "understanding": "家长补充：让孩子自己选择先做哪科时更容易开始。",
            "hypotheses": [{"statement": "选择顺序可能比学习意愿更值得先验证。"}],
        },
        idempotency_key="create:follow-up-run",
    )

    async with engine.begin() as connection:
        repository = SqlAlchemyAssessmentRepository(connection)
        commands = AssessmentCommandHandler(repository)
        interpretation = DeterministicInterpretationAdapter()
        queries = AssessmentQueryHandler(repository, interpretation)
        decisions = GrowthHypothesisCommandHandler(repository, interpretation)

        started = await commands.start(
            StartAssessmentCommand(
                family_id,
                tenant_id,
                guardian_id,
                child_id,
                None,
                _meta("scenario:start"),
            )
        )
        assessment_session_id = started["session"]["assessment_session_id"]
        await commands.save_response(
            SaveAssessmentResponseCommand(
                family_id,
                tenant_id,
                guardian_id,
                assessment_session_id,
                "FOCUS",
                "SINGLE_CHOICE",
                "PARENT_CHILD_COMMUNICATION",
                _meta("scenario:answer"),
            )
        )
        submitted = await commands.submit(
            SubmitAssessmentCommand(
                family_id,
                tenant_id,
                guardian_id,
                assessment_session_id,
                _meta("scenario:submit"),
            )
        )
        projection = await queries.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, tenant_id, guardian_id)
        )
        hypothesis = projection["hypothesis"]
        assert submitted["session"]["status"] == "SUBMITTED"
        assert projection["availability"] == "READY"
        assert hypothesis["fact_boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"
        assert hypothesis["limitations"]
        assert hypothesis["action_candidate_refs"]

        decision = await decisions.decide(
            DecideGrowthHypothesisCommand(
                family_id,
                tenant_id,
                guardian_id,
                assessment_session_id,
                hypothesis["hypothesis_ref"],
                "CONFIRM",
                "scenario-correlation",
                "scenario:confirm-next-step",
            )
        )
        assert decision["outcome"] == "INTENT_CREATED"
        assert decision["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"

    await engine.dispose()

    restarted_engine = create_async_engine(migrated_database_url)
    restarted_experience = SessionPerCallExperienceRunLedger(
        async_sessionmaker(restarted_engine, expire_on_commit=False)
    )
    replayed = await restarted_experience.replay(scope=scope, run_id="follow-up-run")
    assert replayed.draft_payload is not None
    assert replayed.draft_payload["prior_run_id"] == "concern-run"
    async with restarted_engine.connect() as connection:
        session_status = await connection.scalar(
            text(
                "select status from family_assessment_sessions "
                "where assessment_session_id=:session_id"
            ),
            {"session_id": assessment_session_id},
        )
        intent_count = await connection.scalar(
            text(
                "select count(*) from growth_intents "
                "where family_id=:family_id and subject_person_id=:subject_id"
            ),
            {"family_id": family_id, "subject_id": child_id},
        )
    assert session_status == "SUBMITTED"
    assert intent_count == 1
    await restarted_engine.dispose()
