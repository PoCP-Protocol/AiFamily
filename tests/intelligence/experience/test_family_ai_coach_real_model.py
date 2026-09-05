"""Real-model verification for the AI Coach — the only real evidence here.

Every other AI Coach test uses `FakeProvider`, which is deterministic
infrastructure, not proof that a real model can produce Socratic guidance
(see `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §4 item 3 — a deterministic
fallback must never be presented as an AI capability). This test is gated on
`AI_COACH_MODEL_API_KEY` / `AI_COACH_MODEL_BASE_URL` being set and calls the
real DeepSeek endpoint through `ModelGateway` exactly as production code
would.

## What this test asserts, and deliberately does not assert

It does not assert `guiding_question == "<some fixed string>"` — the model's
wording differs run to run, and pinning it would make this a snapshot test of
one lucky response rather than a check that generation is real. What it
checks instead:

* `guiding_question` is a real question (contains a Chinese or ASCII question
  mark, or an unambiguous interrogative particle), non-empty, and of a
  plausible length for a guiding question rather than a one-word stub.
* `guiding_question` is not itself a solution/instruction sentence — it must
  read as a question, not a disguised piece of advice; the schema forbids an
  "answer"/"solution" field entirely, so this is a content-shape check on top
  of that structural guarantee.
* `reflection` is non-empty prose distinct from `guiding_question` (a model
  that echoes the same sentence into both fields is not doing the two-part
  Socratic job the system prompt asks for).
* Provenance identifies the real provider/model actually invoked.

On failure, the assertion message includes the full prompt payload sent and
the raw model output received, so a human can inspect exactly what the real
model was asked and what it said — the evidence this task exists to produce.
"""

from __future__ import annotations

import os

import pytest

from backend.apps.family_api.ai_coach_wiring import (
    AI_COACH_DEEPSEEK_PROVIDER_ID,
    build_livecheck_deepseek_coach_gateway,
    deepseek_coach_credentials_available,
)
from backend.intelligence.experience.family_ai_coach import (
    COACH_SYSTEM_PROMPT,
    coach_reply,
)

pytestmark = pytest.mark.skipif(
    not deepseek_coach_credentials_available(),
    reason=(
        "AI_COACH_MODEL_API_KEY / AI_COACH_MODEL_BASE_URL not set — this is the "
        "gated real-model verification test. Set both environment variables to "
        "a real DeepSeek endpoint (base_url=https://api.deepseek.com/v1, "
        "model=deepseek-chat) to actually run it. See CLAUDE.md / the AI Coach "
        "task instructions for why this must not run with FakeProvider."
    ),
)

_REAL_PARENT_MESSAGE = "孩子写作业拖延，已经上过一门课但没完全解决"
_REAL_FAMILY_CONTEXT = {
    "need_statement": "孩子写作业拖延，已经上过一门课但没完全解决",
    "desired_outcome": "希望孩子能自己按时开始写作业",
    "category": "EDUCATION",
    "emotional_gate": "E0_WELCOME",
}


def _looks_like_a_question(text: str) -> bool:
    return any(marker in text for marker in ("？", "?", "吗", "呢"))


@pytest.mark.asyncio
async def test_real_deepseek_call_produces_a_genuine_socratic_question() -> None:
    gateway = build_livecheck_deepseek_coach_gateway(env=os.environ)

    perspective = await coach_reply(
        gateway,
        provider_id=AI_COACH_DEEPSEEK_PROVIDER_ID,
        family_context=_REAL_FAMILY_CONTEXT,
        parent_message=_REAL_PARENT_MESSAGE,
        tenant_id="livecheck-tenant",
        family_id="livecheck-family",
        context_snapshot_ref="livecheck-context-ref-001",
        # OPERATIONAL_TEXT, not FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA: this
        # is a synthetic verification scenario run against a provider with no
        # completed §16 assessment (see `ai_coach_wiring.py`). Real family
        # data must never be sent through this provider_id/data_class pair.
        data_class="OPERATIONAL_TEXT",
    )

    evidence = (
        "\n--- REAL MODEL CALL EVIDENCE ---\n"
        f"system_prompt={COACH_SYSTEM_PROMPT!r}\n"
        f"parent_message={_REAL_PARENT_MESSAGE!r}\n"
        f"family_context={_REAL_FAMILY_CONTEXT!r}\n"
        f"model={perspective.provenance.model!r}\n"
        f"provider_id={perspective.provenance.provider_id!r}\n"
        f"reflection={perspective.reflection!r}\n"
        f"guiding_question={perspective.guiding_question!r}\n"
        f"boundary_note={perspective.boundary_note!r}\n"
        "--- END EVIDENCE ---\n"
    )

    assert perspective.provenance.provider_id == AI_COACH_DEEPSEEK_PROVIDER_ID, evidence
    assert perspective.provenance.model, evidence
    assert isinstance(perspective.guiding_question, str), evidence
    assert len(perspective.guiding_question.strip()) >= 6, evidence
    assert _looks_like_a_question(perspective.guiding_question), evidence
    assert isinstance(perspective.reflection, str), evidence
    assert len(perspective.reflection.strip()) >= 6, evidence
    assert perspective.reflection.strip() != perspective.guiding_question.strip(), evidence
    # The schema has no "answer"/"solution" field to begin with, but this
    # restates the intent at the content level: a genuine guiding question
    # should not read as an imperative instruction sentence.
    assert not perspective.guiding_question.strip().startswith(("你应该", "建议你", "你需要")), (
        evidence
    )
