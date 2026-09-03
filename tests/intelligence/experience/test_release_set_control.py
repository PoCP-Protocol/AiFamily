from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import (
    InMemoryReleaseSetControlStore,
    ReleaseSetControlBase,
    ReleaseSetControlError,
    SqlAlchemyReleaseSetControlStore,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _release_set(marker: str) -> FamilyExperienceReleaseSet:
    return FamilyExperienceReleaseSet(
        release_set_id=marker * 64,
        environment="staging",
        use_case="family_assistant_conversation",
        data_class="OPERATIONAL_TEXT",
        provider_ids=("provider-a",),
        bundle_ids=(marker.upper() * 64,),
        routing_policy_version="routing.v1",
        route_config_digest="1" * 64,
        rate_card_version="rates.v1",
        rate_card_digest="2" * 64,
        budget_policy_version="budget.v1",
        budget_policy_digest="3" * 64,
        agent_id="parent_advisor",
        prompt_ref="prompt:family",
        prompt_version="prompt.v1",
        schema_ref="schema:family",
        schema_version="schema.v1",
        safety_policy_version="safety.v1",
        safety_policy_digest="5" * 64,
        knowledge_refs=("knowledge:family",),
        asset_digest="4" * 64,
        runtime_config_digest=marker * 64,
    )


class _Verifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.payloads: list[dict[str, object]] = []

    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        self.payloads.append(json.loads(payload))
        return self.accepted and signature == "valid-signature" and bool(actor_id)


async def _authorize(store, source, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "kind": "APPLY",
        "phase": "ACTIVE",
        "rollout_percent": 100,
        "target": None,
        "expected_effective_sequence": 0,
        "actor_id": "operator:release",
        "idempotency_key": "control:apply:a",
        "reason": "reviewed release activation",
        "signature": "valid-signature",
        "signature_algorithm": "external-kms-v1",
    }
    values.update(overrides)
    return await store.authorize(source, **values)


@pytest.mark.asyncio
async def test_signed_control_covers_exact_release_scope_digest_and_sequence() -> None:
    verifier = _Verifier()
    store = InMemoryReleaseSetControlStore(
        signature_verifier=verifier,
        clock=lambda: NOW,
    )
    source = _release_set("a")

    event = await _authorize(store, source)
    replay = await _authorize(store, source)

    assert replay == event
    assert await store.get(event.control_id) == event
    assert verifier.payloads[0] == {
        "actor_id": "operator:release",
        "data_class": source.data_class,
        "environment": source.environment,
        "expected_effective_sequence": 0,
        "idempotency_key": "control:apply:a",
        "kind": "APPLY",
        "phase": "ACTIVE",
        "rollout_percent": 100,
        "reason": "reviewed release activation",
        "runtime_config_digest": source.runtime_config_digest,
        "signature_algorithm": "external-kms-v1",
        "source_release_set_id": source.release_set_id,
        "target_release_set_id": None,
        "use_case": source.use_case,
    }


@pytest.mark.asyncio
async def test_unsigned_or_ai_control_is_rejected() -> None:
    source = _release_set("a")
    rejected = InMemoryReleaseSetControlStore(
        signature_verifier=_Verifier(accepted=False),
        clock=lambda: NOW,
    )
    with pytest.raises(ReleaseSetControlError, match="SIGNATURE_INVALID"):
        await _authorize(rejected, source)

    accepted = InMemoryReleaseSetControlStore(
        signature_verifier=_Verifier(),
        clock=lambda: NOW,
    )
    with pytest.raises(ReleaseSetControlError, match="AI_RELEASE_SET_CONTROLLER"):
        await _authorize(accepted, source, actor_id="ai:release-bot")


@pytest.mark.asyncio
async def test_sql_control_round_trip_keeps_signed_metadata_only() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ReleaseSetControlBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        store = SqlAlchemyReleaseSetControlStore(
            session,
            signature_verifier=_Verifier(),
            clock=lambda: NOW,
        )
        event = await _authorize(store, _release_set("a"))
    async with factory() as session:
        restored = await SqlAlchemyReleaseSetControlStore(
            session,
            signature_verifier=_Verifier(),
        ).get(event.control_id)
    assert restored == event
    await engine.dispose()
