from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.outcome_reflection import (
    OutcomeReflectionContextWriter,
)

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _scope(family_id: str = "family-a") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-a",
        region_id="CN",
        family_id=family_id,
        subject_ids=("child-a",),
        purpose="family-growth-understanding",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="delete:a",
        correlation_id="corr:a",
        causation_id="cause:a",
    )


class _Broker:
    durability_mode = "DURABLE"

    def __init__(self):
        self.observations = []

    async def append(self, observation):
        self.observations.append(observation)


def _outcome(family_id: str = "family-a", **changes):
    values = dict(
        outcome_id="outcome-1",
        need_id="need-1",
        fulfillment_ref="action-1",
        decision="HELPED",
        confirmed_by="guardian-1",
        confirmed_at=NOW,
        family_id=family_id,
        tenant_id="tenant-a",
        subject_ids=("child-a",),
        consent_version="consent-v1",
        deletion_ref="delete:a",
    )
    values.update(changes)
    return SimpleNamespace(**values)


def _canonical_outcome():
    context = SimpleNamespace(
        tenant_id="tenant-a",
        family_id="family-a",
        subject_person_ids=("child-a",),
        consent_version="consent-v1",
        deletion_ref="delete:a",
    )
    return SimpleNamespace(
        outcome_id="outcome-canonical",
        need_id="need-1",
        fulfillment_ref="action-1",
        decision=SimpleNamespace(value="HELPED"),
        confirmed_by="guardian-1",
        confirmed_at=NOW,
        context=context,
        family_note=None,
    )


@pytest.mark.asyncio
async def test_confirmed_outcome_is_projected_as_retained_observation() -> None:
    broker = _Broker()
    await OutcomeReflectionContextWriter(broker).record(_outcome(), scope=_scope())

    observation = broker.observations[0]
    assert observation.dimension == "confirmed_outcome_reflection"
    assert "outcome-1" in observation.observed_value
    assert observation.expires_at == NOW + timedelta(days=90)
    assert observation.provenance == "family-need:confirmed-outcome"
    assert observation.evidence_refs == ("family-outcome:outcome-1",)
    assert observation.causation_id == "family-need:need-1"
    decoded = __import__("json").loads(observation.observed_value)
    assert decoded["reflection"] is None
    assert decoded["feedback_ref"] == "outcome:outcome-1:HELPED"
    assert decoded["confirmed_at"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_canonical_family_need_outcome_uses_explicit_context_projection() -> None:
    broker = _Broker()
    await OutcomeReflectionContextWriter(broker).record_family_need_outcome(
        _canonical_outcome(), scope=_scope()
    )

    observation = broker.observations[0]
    assert observation.subject_id == "child-a"
    assert "outcome-canonical" in observation.observed_value


@pytest.mark.asyncio
async def test_outcome_family_note_is_bounded_reflection_material() -> None:
    broker = _Broker()
    await OutcomeReflectionContextWriter(broker).record(
        _outcome(family_note="  这次练习后冲突少了一些。  "), scope=_scope()
    )
    assert __import__("json").loads(broker.observations[0].observed_value)["reflection"] == (
        "这次练习后冲突少了一些。"
    )


@pytest.mark.asyncio
async def test_outcome_reflection_rejects_scope_version_or_deletion_mismatch() -> None:
    writer = OutcomeReflectionContextWriter(_Broker())
    with pytest.raises(ValueError, match="consent version"):
        await writer.record(_outcome(consent_version="consent-old"), scope=_scope())
    with pytest.raises(ValueError, match="deletion scope"):
        await writer.record(_outcome(deletion_ref="delete-old"), scope=_scope())


@pytest.mark.asyncio
async def test_outcome_reflection_rejects_oversized_note() -> None:
    with pytest.raises(ValueError, match="note invalid"):
        await OutcomeReflectionContextWriter(_Broker()).record(
            _outcome(family_note="x" * 2001), scope=_scope()
        )


@pytest.mark.asyncio
async def test_outcome_reflection_rejects_cross_family_projection() -> None:
    with pytest.raises(ValueError, match="scope mismatch"):
        await OutcomeReflectionContextWriter(_Broker()).record(
            _outcome("family-other"), scope=_scope()
        )


@pytest.mark.asyncio
async def test_outcome_reflection_rejects_missing_deletion_scope() -> None:
    outcome = _outcome()
    del outcome.deletion_ref
    with pytest.raises(ValueError, match="deletion scope required"):
        await OutcomeReflectionContextWriter(_Broker()).record(outcome, scope=_scope())
