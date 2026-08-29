"""Unit tests for the Assessment domain command/query handlers, run against
the in-memory `FakeAssessmentRepository`. These exercise the ported behavior
of `AssessmentService`/`GrowthHypothesisService` (NestJS) end-to-end at the
application layer, without HTTP or a real database — per migration plan
section 9's "FakeProvider" requirement.
"""

from __future__ import annotations

import uuid

import pytest

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
from backend.domains.assessment.application.queries import (
    AssessmentQueryHandler,
    GetUi02ProjectionQuery,
    GetUi03ProjectionQuery,
)
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentValidationError,
)
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository

TENANT_ID = "tenant-1"


def _meta(key: str = "idem-1") -> MutationMeta:
    return MutationMeta(correlation_id="corr-1", idempotency_key=key, source="test")


@pytest.fixture
def repo() -> FakeAssessmentRepository:
    repository = FakeAssessmentRepository()
    family_id = str(uuid.uuid4())
    repository.seed_family(TENANT_ID, family_id)
    child_id = str(uuid.uuid4())
    repository.seed_subject(family_id, child_id, "小明")
    repository.seed_need_type(
        "COMMUNICATION",
        "NEED_PARENT_CHILD_COMMUNICATION",
        "亲子沟通支持",
        "先从倾听开始",
        ["LISTENING_COACH"],
    )
    repository._test_family_id = family_id  # type: ignore[attr-defined]
    repository._test_child_id = child_id  # type: ignore[attr-defined]
    return repository


@pytest.fixture
def command_handler(repo: FakeAssessmentRepository) -> AssessmentCommandHandler:
    return AssessmentCommandHandler(repo)


@pytest.fixture
def interpretation() -> DeterministicInterpretationAdapter:
    return DeterministicInterpretationAdapter()


@pytest.fixture
def query_handler(
    repo: FakeAssessmentRepository, interpretation: DeterministicInterpretationAdapter
) -> AssessmentQueryHandler:
    return AssessmentQueryHandler(repo, interpretation)


@pytest.fixture
def growth_hypothesis_handler(
    repo: FakeAssessmentRepository, interpretation: DeterministicInterpretationAdapter
) -> GrowthHypothesisCommandHandler:
    return GrowthHypothesisCommandHandler(repo, interpretation)


class TestAssessmentSessionLifecycle:
    async def test_start_creates_in_progress_session(self, repo, command_handler):
        family_id, child_id = repo._test_family_id, repo._test_child_id
        receipt = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta())
        )
        assert receipt["action"] == "START_ASSESSMENT"
        assert receipt["replayed"] is False
        assert receipt["session"]["status"] == "IN_PROGRESS"
        assert receipt["boundary"] == "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS"

    async def test_start_is_idempotent_on_replay(self, repo, command_handler):
        family_id, child_id = repo._test_family_id, repo._test_child_id
        meta = _meta("idem-replay")
        first = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, meta)
        )
        second = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, meta)
        )
        assert second["replayed"] is True
        assert (
            second["session"]["assessment_session_id"] == first["session"]["assessment_session_id"]
        )

    async def test_start_without_consent_is_forbidden(self, repo, command_handler):
        family_id = repo._test_family_id
        no_consent_child = str(uuid.uuid4())
        repo.seed_subject(family_id, no_consent_child, "小红", consent_granted=False)
        with pytest.raises(AssessmentForbiddenError) as exc:
            await command_handler.start(
                StartAssessmentCommand(
                    family_id, TENANT_ID, "actor-1", no_consent_child, None, _meta()
                )
            )
        assert exc.value.code == "assessment_subject_or_consent_unavailable"

    async def test_save_response_then_submit_creates_evidence(self, repo, command_handler):
        family_id, child_id = repo._test_family_id, repo._test_child_id
        start = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta("s1"))
        )
        session_id = start["session"]["assessment_session_id"]

        save = await command_handler.save_response(
            SaveAssessmentResponseCommand(
                family_id,
                TENANT_ID,
                "actor-1",
                session_id,
                "FOCUS",
                "SINGLE_CHOICE",
                "COMMUNICATION",
                _meta("s2"),
            )
        )
        assert save["session"]["responses"][0]["item_ref"] == "FOCUS"

        submit = await command_handler.submit(
            SubmitAssessmentCommand(family_id, TENANT_ID, "actor-1", session_id, _meta("s3"))
        )
        assert submit["session"]["status"] == "SUBMITTED"
        assert submit["evidence_id"] is not None
        assert submit["boundary"] == "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS"

    async def test_submit_after_submitted_is_conflict(self, repo, command_handler):
        family_id, child_id = repo._test_family_id, repo._test_child_id
        start = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta("c1"))
        )
        session_id = start["session"]["assessment_session_id"]
        await command_handler.save_response(
            SaveAssessmentResponseCommand(
                family_id,
                TENANT_ID,
                "actor-1",
                session_id,
                "FOCUS",
                "SINGLE_CHOICE",
                "COMMUNICATION",
                _meta("c2"),
            )
        )
        await command_handler.submit(
            SubmitAssessmentCommand(family_id, TENANT_ID, "actor-1", session_id, _meta("c3"))
        )
        with pytest.raises(AssessmentConflictError) as exc:
            await command_handler.submit(
                SubmitAssessmentCommand(family_id, TENANT_ID, "actor-1", session_id, _meta("c4"))
            )
        assert exc.value.code == "assessment_session_not_editable"

    async def test_save_response_with_invalid_choice_is_rejected(self, repo, command_handler):
        family_id, child_id = repo._test_family_id, repo._test_child_id
        start = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta("v1"))
        )
        session_id = start["session"]["assessment_session_id"]
        with pytest.raises(AssessmentValidationError) as exc:
            await command_handler.save_response(
                SaveAssessmentResponseCommand(
                    family_id,
                    TENANT_ID,
                    "actor-1",
                    session_id,
                    "FOCUS",
                    "SINGLE_CHOICE",
                    "NOT_A_REAL_OPTION",
                    _meta("v2"),
                )
            )
        assert exc.value.code == "assessment_choice_not_in_tool_version"


class TestUi02Projection:
    async def test_projection_shows_available_when_consent_granted(self, repo, query_handler):
        family_id = repo._test_family_id
        projection = await query_handler.get_ui02_projection(
            GetUi02ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        assert projection["availability"] == "AVAILABLE"
        assert projection["tool"]["tool_ref"] == "FAMILY_SUPPORT_NEEDS"
        assert projection["named_actions"]["submit"] == "SUBMIT_ASSESSMENT"


class TestGrowthHypothesisFlow:
    async def _submit_full_session(self, repo, command_handler) -> str:
        family_id, child_id = repo._test_family_id, repo._test_child_id
        start = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta("h1"))
        )
        session_id = start["session"]["assessment_session_id"]
        await command_handler.save_response(
            SaveAssessmentResponseCommand(
                family_id,
                TENANT_ID,
                "actor-1",
                session_id,
                "FOCUS",
                "SINGLE_CHOICE",
                "COMMUNICATION",
                _meta("h2"),
            )
        )
        await command_handler.submit(
            SubmitAssessmentCommand(family_id, TENANT_ID, "actor-1", session_id, _meta("h3"))
        )
        return session_id

    async def test_ui03_projection_ready_after_submission(
        self, repo, command_handler, query_handler
    ):
        await self._submit_full_session(repo, command_handler)
        family_id = repo._test_family_id
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        assert projection["availability"] == "READY"
        assert projection["hypothesis"]["fact_boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"
        assert "hypothesis_not_fact" in projection["hypothesis"]["model_boundary_labels"]

    async def test_ui03_projection_no_submitted_assessment_before_submit(self, repo, query_handler):
        family_id = repo._test_family_id
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        assert projection["availability"] == "NO_SUBMITTED_ASSESSMENT"
        assert projection["hypothesis"] is None

    async def test_confirm_decision_creates_growth_intent_with_boundary(
        self, repo, command_handler, query_handler, growth_hypothesis_handler
    ):
        session_id = await self._submit_full_session(repo, command_handler)
        family_id = repo._test_family_id
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        hypothesis_ref = projection["hypothesis"]["hypothesis_ref"]

        receipt = await growth_hypothesis_handler.decide(
            DecideGrowthHypothesisCommand(
                family_id,
                TENANT_ID,
                "actor-1",
                session_id,
                hypothesis_ref,
                "CONFIRM",
                "corr-2",
                "decide-1",
            )
        )
        assert receipt["outcome"] == "INTENT_CREATED"
        assert receipt["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"

    async def test_dismiss_decision_does_not_create_intent(
        self, repo, command_handler, query_handler, growth_hypothesis_handler
    ):
        session_id = await self._submit_full_session(repo, command_handler)
        family_id = repo._test_family_id
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        hypothesis_ref = projection["hypothesis"]["hypothesis_ref"]

        receipt = await growth_hypothesis_handler.decide(
            DecideGrowthHypothesisCommand(
                family_id,
                TENANT_ID,
                "actor-1",
                session_id,
                hypothesis_ref,
                "DISMISS",
                "corr-3",
                "decide-2",
            )
        )
        assert receipt["outcome"] == "NO_ACTION"
        assert receipt["intent"] is None

    async def test_stale_hypothesis_ref_is_conflict(
        self, repo, command_handler, growth_hypothesis_handler
    ):
        session_id = await self._submit_full_session(repo, command_handler)
        family_id = repo._test_family_id
        with pytest.raises(AssessmentConflictError) as exc:
            await growth_hypothesis_handler.decide(
                DecideGrowthHypothesisCommand(
                    family_id,
                    TENANT_ID,
                    "actor-1",
                    session_id,
                    "STALE:REF:H1",
                    "CONFIRM",
                    "corr-4",
                    "decide-3",
                )
            )
        assert exc.value.code == "growth_hypothesis_reference_mismatch"


class TestSafetyPolicy:
    """Direct unit tests on the ported `assess_structured_safety_signals` —
    same three-tier severity/disposition mapping as
    `safety-assessment.policy.ts`.
    """

    def test_none_signal_is_normal(self):
        from backend.domains.assessment.domain.policies import assess_structured_safety_signals

        result = assess_structured_safety_signals(["NONE"])
        assert result.severity == "LOW"
        assert result.disposition == "NORMAL"

    def test_self_harm_is_critical(self):
        from backend.domains.assessment.domain.policies import assess_structured_safety_signals

        result = assess_structured_safety_signals(["SELF_HARM"])
        assert result.severity == "CRITICAL"
        assert result.disposition == "SAFETY_ESCALATION"

    def test_abuse_is_high_not_critical(self):
        from backend.domains.assessment.domain.policies import assess_structured_safety_signals

        result = assess_structured_safety_signals(["ABUSE"])
        assert result.severity == "HIGH"
        assert result.disposition == "SAFETY_ESCALATION"
