"""Default (mock/fail-closed) interpretation adapter — port of the
`interpretDeterministically` fallback path in `family-model`'s
`FamilyEducationModelRuntime`. Per G1-A's binding default
(`governance/AUTHORIZATION_REGISTRY.yaml`, `.env.example` mock/fail-closed),
this is what runs when no live provider is configured: deterministic,
rule-based, no external call. A real `AiRuntimeInterpretationAdapter` that
calls the Python AI Runtime process is a later step in this task — the
migration plan's own acceptance criterion #9 ("provider failure fails
closed, explicitly") means this fallback path must exist and be correct
before a live path is added, not after.

Boundary labels (`hypothesis_not_fact`, `recommendation_not_decision`,
`signal_not_diagnosis`) and the construct-ref whitelist rule are the same
fail-closed guarantees `assertInterpretationBoundary` enforces in the
TypeScript version — see migration plan section 10.

AI Run Ledger: an optional `AiRunLedgerPort` may be injected (constructor
arg, defaulted to `None` for backward compatibility with existing call
sites). When present, every `interpret()` call — including this fallback
path with no external call — writes one `AiRunRecord` with
`generator="deterministic"`, so the ledger can distinguish "this session's
draft came from the rule-based fallback" from "this session's draft came
from the live model", which is exactly the audit gap migration plan §9's
"AI Run Ledger" item exists to close. See `domain/ai_run.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..application.ports import AiRunLedgerPort, AssessmentInterpretationPort
from ..domain.ai_run import AiRunRecord
from ..domain.entities import GrowthHypothesisEvidence

_LEGAL_CONSTRUCT_REFS = {
    "PARENT_CHILD_COMMUNICATION",
    "HOMEWORK_PROCESS",
    "DEVICE_USE_CONTEXT",
}

_FOCUS_TO_CONSTRUCT = {
    "COMMUNICATION": "PARENT_CHILD_COMMUNICATION",
    "HOMEWORK": "HOMEWORK_PROCESS",
    "SCREEN_TIME": "DEVICE_USE_CONTEXT",
}


class DeterministicInterpretationAdapter(AssessmentInterpretationPort):
    """No external call. Produces a structurally valid interpretation draft
    from the evidence alone — same shape a real AI Runtime response would
    have, so the application layer (`_map_hypothesis`) doesn't need to know
    which adapter is behind the port.
    """

    def __init__(self, ai_run_ledger: AiRunLedgerPort | None = None):
        # Optional, defaulted — existing call sites that construct this
        # adapter with no arguments (tests, prior wiring) keep working
        # unchanged; the ledger dependency is additive, not breaking.
        self._ai_run_ledger = ai_run_ledger

    async def interpret(
        self, family_id: str, evidence: GrowthHypothesisEvidence, service_depth: str = "DEEP_AI_INTERPRETATION"
    ) -> dict:
        started_at = datetime.now(timezone.utc)
        construct_ref = _FOCUS_TO_CONSTRUCT.get(evidence.focus_ref)
        construct_signals = []
        if construct_ref in _LEGAL_CONSTRUCT_REFS:
            construct_signals = [
                {
                    "construct_ref": construct_ref,
                    "boundary": "signal_not_diagnosis",
                }
            ]

        hypothesis_ref = f"{evidence.assessment_session_id}:H1"
        draft = {
            "model_component_ref": "FAMILY_ASSESSMENT_V0_COMPONENT",
            "assessment_ref": evidence.assessment_session_id,
            "boundary_labels": ["hypothesis_not_fact", "recommendation_not_decision"],
            "need_summary": [{"need_ref": evidence.need_type_ref}],
            "construct_signals": construct_signals,
            "hypotheses": [
                {
                    "hypothesis_ref": hypothesis_ref,
                    "boundary": "hypothesis_not_fact",
                    "construct_refs": [construct_ref] if construct_ref else [],
                    # Deterministic fallback only ever produces a single hypothesis
                    # (H1 above), so it is trivially "the" primary contradiction —
                    # rank 1, no ambiguity to resolve without a model. Mirrors the
                    # same field ClaudeInterpretationAdapter's structured output
                    # carries, per the adapters' shared-shape requirement.
                    "is_primary_contradiction": True,
                    "contradiction_rank": 1,
                }
            ],
            "action_candidates": [
                {
                    "action_ref": f"{evidence.need_type_ref}:SUPPORT_ACTION",
                    "boundary": "recommendation_not_decision",
                }
            ],
            "human_gate": {"required": False, "reason_refs": []},
            "prohibited_outputs": [],
        }

        # Ledger entry even though no external call happened — the point of
        # this record is precisely "this session's interpretation went
        # through the fallback path, not the live gateway", which matters
        # for anyone auditing why a family got a deterministic draft.
        if self._ai_run_ledger is not None:
            await self._ai_run_ledger.record(
                AiRunRecord(
                    run_id=str(uuid.uuid4()),
                    assessment_session_id=evidence.assessment_session_id,
                    service_depth=service_depth,
                    generator="deterministic",
                    model_name=None,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    input_tokens=None,
                    output_tokens=None,
                    outcome="success",
                    error_detail=None,
                )
            )

        return {
            "subsystem_ref": "FAMILY_ASSESSMENT_AI_SUBSYSTEM",
            "subsystem_version": "0.1.0",
            "service_depth": service_depth,
            "interpretation": {
                "backend_capability_ref": "FAMILY_ASSESSMENT_AI_CAPABILITY",
                "ai_use_case": "ASSESSMENT_INTERPRETATION",
                "generator": "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC",
                "assessment_ref": evidence.assessment_session_id,
                "draft": draft,
            },
            "scorecard": {"generator": "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC"},
        }
