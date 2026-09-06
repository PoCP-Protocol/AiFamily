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
    GetAssessmentResultProjectionQuery,
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

    async def test_projection_records_minor_read_access(self, repo, query_handler):
        family_id = repo._test_family_id

        await query_handler.get_ui02_projection(
            GetUi02ProjectionQuery(family_id, TENANT_ID, "actor-1", "read-correlation-1")
        )

        assert len(repo.read_audit_events) == 1
        event = repo.read_audit_events[0]
        assert event.is_read
        assert event.subject_person_id == repo._test_child_id
        assert event.access_purpose == "ASSESSMENT"
        assert event.correlation_id == "read-correlation-1"
        assert "display_name" in event.accessed_fields

    async def test_policy_block_does_not_read_child_projection(self, repo, query_handler):
        family_id = repo._test_family_id
        repo.tenant_allowed_pages[TENANT_ID].remove("UI-02")

        projection = await query_handler.get_ui02_projection(
            GetUi02ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )

        assert projection["availability"] == "POLICY_BLOCKED"
        assert projection["subjects"] == []
        assert repo.read_audit_events == []

    async def test_read_audit_failure_blocks_projection(self, repo, interpretation):
        class _FailingReadAuditRepository:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            async def record_read_access(self, **kwargs):
                raise RuntimeError("read audit unavailable")

        handler = AssessmentQueryHandler(
            _FailingReadAuditRepository(repo), interpretation
        )
        with pytest.raises(RuntimeError, match="read audit unavailable"):
            await handler.get_ui02_projection(
                GetUi02ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")
            )


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
        assert len(repo.read_audit_events) == 1
        event = repo.read_audit_events[0]
        assert event.is_read
        assert event.subject_person_id == repo._test_child_id
        assert event.approval_ref == f"consent:ASSESSMENT:{repo._test_child_id}"

    async def test_ui03_withdrawn_consent_hides_evidence_and_records_no_read(
        self, repo, command_handler, query_handler
    ):
        await self._submit_full_session(repo, command_handler)
        repo.consents.remove((repo._test_family_id, repo._test_child_id, "ASSESSMENT"))

        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")
        )

        assert projection["availability"] == "NO_SUBMITTED_ASSESSMENT"
        assert projection["hypothesis"] is None
        assert repo.read_audit_events == []

    async def test_decision_checks_consent_before_interpretation(
        self, repo, command_handler, query_handler
    ):
        session_id = await self._submit_full_session(repo, command_handler)
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")
        )
        hypothesis_ref = projection["hypothesis"]["hypothesis_ref"]
        repo.consents.remove((repo._test_family_id, repo._test_child_id, "ASSESSMENT"))

        class _MustNotInterpret:
            async def interpret(self, *args, **kwargs):
                raise AssertionError("withdrawn child evidence reached interpretation")

        class _StaleEvidenceRepository:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            async def load_hypothesis_evidence(self, family_id, tenant_id, session_id=None):
                # Simulate a stale repository/cache returning evidence even
                # though the current consent was withdrawn. The command's
                # explicit pre-interpretation consent check must still stop it.
                self._inner.consents.add((family_id, repo._test_child_id, "ASSESSMENT"))
                try:
                    return await self._inner.load_hypothesis_evidence(
                        family_id, tenant_id, session_id
                    )
                finally:
                    self._inner.consents.remove((family_id, repo._test_child_id, "ASSESSMENT"))

        handler = GrowthHypothesisCommandHandler(
            _StaleEvidenceRepository(repo), _MustNotInterpret()
        )
        with pytest.raises(AssessmentForbiddenError) as exc:
            await handler.decide(
                DecideGrowthHypothesisCommand(
                    repo._test_family_id,
                    TENANT_ID,
                    "actor-1",
                    session_id,
                    hypothesis_ref,
                    "CONFIRM",
                    "corr-withdrawn",
                    "decision-withdrawn",
                )
            )
        assert exc.value.code == "assessment_subject_or_consent_unavailable"

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

    async def test_ai_actor_confirmation_is_denied_even_with_guardian_scoped_person_id(
        self, repo, command_handler, query_handler, growth_hypothesis_handler
    ):
        """R9 regression: `assert_tenant_family_scope` only proves family
        membership, not that the caller is human. A person_id that resolves
        to an AI or SYSTEM service account (e.g. one holding a
        GUARDIAN-shaped membership row) must still be denied by the
        `PolicyEngine` `human_only` veto in `GrowthHypothesisCommandHandler.
        decide` — not merely by an application convention that happens to
        pass a human actor_id today.
        """
        from backend.platform.identity.context import ActorType as PlatformActorType

        session_id = await self._submit_full_session(repo, command_handler)
        family_id = repo._test_family_id
        projection = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        hypothesis_ref = projection["hypothesis"]["hypothesis_ref"]

        for actor_type in (PlatformActorType.AI, PlatformActorType.SYSTEM):
            with pytest.raises(AssessmentForbiddenError) as exc:
                await growth_hypothesis_handler.decide(
                    DecideGrowthHypothesisCommand(
                        family_id,
                        TENANT_ID,
                        "actor-1",  # same person_id a human guardian would use
                        session_id,
                        hypothesis_ref,
                        "CONFIRM",
                        "corr-r9",
                        f"decide-r9-{actor_type.value}",
                        actor_type=actor_type,
                    )
                )
            assert exc.value.code == "growth_hypothesis_confirmation_requires_human_actor"

        # No intent must have been created by either denied attempt.
        projection_after = await query_handler.get_ui03_projection(
            GetUi03ProjectionQuery(family_id, TENANT_ID, "actor-1")
        )
        assert projection_after["hypothesis"]["hypothesis_ref"] == hypothesis_ref

    async def test_human_actor_confirmation_still_succeeds_after_r9_check(
        self, repo, command_handler, query_handler, growth_hypothesis_handler
    ):
        """The R9 veto must deny AI/SYSTEM only — a genuine human guardian's
        confirmation must not be collaterally blocked by the same check."""
        from backend.platform.identity.context import ActorType as PlatformActorType

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
                "corr-r9-human",
                "decide-r9-human",
                actor_type=PlatformActorType.HUMAN,
            )
        )
        assert receipt["outcome"] == "INTENT_CREATED"


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {key for key in value} | {
            nested_key for nested in value.values() for nested_key in _nested_keys(nested)
        }
    if isinstance(value, list):
        return {nested_key for nested in value for nested_key in _nested_keys(nested)}
    return set()


class TestAssessmentResultProjection:
    """`GET /families/{family_id}/assessments/results/latest` — a read-only
    projection derived from the submitted session/evidence. It must never
    expose a score or ranking (R9), and must fail closed on withdrawn
    consent rather than serving a stale cached result.
    """

    async def _submit_full_session(self, repo, command_handler) -> str:
        family_id, child_id = repo._test_family_id, repo._test_child_id
        start = await command_handler.start(
            StartAssessmentCommand(family_id, TENANT_ID, "actor-1", child_id, None, _meta("r1"))
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
                _meta("r2"),
            )
        )
        await command_handler.submit(
            SubmitAssessmentCommand(family_id, TENANT_ID, "actor-1", session_id, _meta("r3"))
        )
        return session_id

    async def test_result_projection_is_family_scoped_and_has_no_score_shape(
        self, repo, command_handler, query_handler
    ):
        await self._submit_full_session(repo, command_handler)
        projection = await query_handler.get_assessment_result_projection(
            GetAssessmentResultProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")
        )

        assert projection["projection_version"] == "ASSESSMENT_RESULT_V1"
        assert projection["status"] == "READY"
        assert projection["family_id"] == repo._test_family_id
        assert projection["result"]["family_need_ref"] == "NEED_PARENT_CHILD_COMMUNICATION"
        assert projection["result"]["ai"]["may_mutate_business_state"] is False
        assert projection["result"]["ai"]["model_gateway_status"] == "NOT_INVOKED"
        assert len(projection["result"]["dimensions"]) == 5
        assert len(projection["result"]["explanation"]["hypotheses"]) == 2
        assert len(projection["result"]["growth_plan"]["phases"]) == 3
        assert projection["result"]["growth_plan"]["status"] == "DRAFT"
        result_keys = {key.lower() for key in _nested_keys(projection["result"])}
        assert "score" not in result_keys
        assert "ranking" not in result_keys

    async def test_result_projection_is_empty_before_submission(self, repo, query_handler):
        projection = await query_handler.get_assessment_result_projection(
            GetAssessmentResultProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")
        )

        assert projection["status"] == "NO_RESULT"
        assert projection["result"] is None

    async def test_result_projection_hides_submitted_content_after_consent_withdrawal(
        self, repo, command_handler, query_handler
    ):
        """`FakeAssessmentRepository.load_hypothesis_evidence` already filters
        out sessions whose subject consent was withdrawn (see its own
        docstring / implementation), so a withdrawn grant makes the evidence
        look unavailable rather than merely consent-blocked. Either shape is
        fail-closed; this asserts the one main's fake actually produces, so
        that if that behavior regresses to leaking the result, this test
        catches it. The handler's own `assert_subject_consent` re-check
        (exercised by `AssessmentForbiddenError` -> `CONSENT_REQUIRED`) is a
        second, independent fail-closed gate for a real repository where
        evidence lookup and consent are not coupled this way.
        """
        await self._submit_full_session(repo, command_handler)
        family_id, child_id = repo._test_family_id, repo._test_child_id
        repo.consents.remove((family_id, child_id, "ASSESSMENT"))

        projection = await query_handler.get_assessment_result_projection(
            GetAssessmentResultProjectionQuery(family_id, TENANT_ID, "actor-1")
        )

        assert projection["status"] in ("NO_RESULT", "CONSENT_REQUIRED")
        assert projection["result"] is None


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
